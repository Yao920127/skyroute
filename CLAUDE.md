# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

SkyRoute is a flight-fare explorer and price-watch board. It has three parts:

- **Backend**: FastAPI, async SQLAlchemy 2 with asyncpg, PostgreSQL, and Redis or an in-memory cache.
- **Frontend**: React 19, TanStack Query, and liveline (canvas price chart), built with Vite+.
- **Fare data**: all prices come from the Duffel Flights API.

Reference documents:

- The spec is `project.md`.
- How Duffel calls are made is in `public/apidocs.html`, served online at `/apidocs` (scripts live in `public/apidocs*.js` because the CSP forbids inline scripts).
- The visual design system is `DESIGN.md`.

User-facing text, comments, and docs are in Traditional Chinese (Taiwan).

## Commands

The frontend uses the Vite+ CLI `vp`, with bun as the package manager. Don't use npm, pnpm, or npx directly. `AGENTS.md` describes `vp`.

```bash
vp install                 # install deps (after pulling)
vp dev                     # http://localhost:5173, proxies /api → :8000 (override with SKYROUTE_API)
vp check                   # format + lint + type check (vp check --fix to auto-fix)
vp test                    # vitest; tests live in src/**/*.test.ts
vp test -t "formats durations"  # single test by name
vp run build               # tsc + production build
```

`vp check --fix` reformats Markdown. `DESIGN.md`, `project.md`, and `public/apidocs*` are excluded through `fmt.ignorePatterns` in `vite.config.ts`. Keep them excluded so the formatter doesn't rewrite them.

Backend commands, run from `backend/` with uv and Python 3.12:

```bash
uv sync
uv run uvicorn app.main:app_factory --factory --port 8000 --reload --reload-dir app
uv run python -m app.worker --once          # patrol every watch once and exit (without --once: per-minute scheduler)
uv run ruff check app tests && uv run ruff format --check app tests
uv run mypy app                             # strict
uv run pytest --cov                         # CI fails below 80% coverage
uv run pytest tests/test_features.py -k stop  # single file / test
```

Always pass `--reload-dir app`. Without it, uvicorn also watches `.venv`. Bulk file touches there, such as Spotlight indexing, then trigger a reload that hangs: the process keeps port 8000 but stops answering requests.

Running everything:

- **Tests**: integration tests need a real PostgreSQL database `skyroute_test`. Override it with `TEST_DATABASE_URL`. Duffel calls are mocked with respx.
- **Full stack**: `docker compose up -d --build` serves at http://localhost:8080. It runs postgres, redis, the api, the worker, and the nginx web container.
- **Cleanup**: `./clean_cache.sh` clears caches. `-n` previews, `--app` clears the Redis app cache, `--deep` removes `node_modules` and `.venv`.

## Backend architecture (`backend/app/`)

### Layers

| Layer           | Role                             |
| --------------- | -------------------------------- |
| `integrations/` | Anti-corruption layer for Duffel |
| `domain/`       | Pure logic, no I/O               |
| `services/`     | Orchestration                    |
| `api/`          | Thin FastAPI routers             |

`container.py` builds one frozen `Container` that the API and `worker.py` share. It holds:

- the DB engine and session factory;
- the cache;
- the `httpx` clients;
- `DuffelGateway`, `TokenCipher`, `SearchService`, `FxService`, and `Notifier`.

`main.py:app_factory` wires it into the app.

### Duffel integration

- **`duffel_client.py`**
  - `DuffelGateway.client(user_token)` returns a `DuffelClient`. The client is bound either to the server token or to the user's own key, which arrives in the `X-Duffel-Token` header.
  - Each client has a `namespace`: the first 16 hex characters of the key's SHA-256 fingerprint. A token-bucket rate limiter is kept per namespace.
  - Search cache keys are suffixed with `:{namespace}`, so quotes from different accounts never mix.
- **Rate limits**: Duffel test accounts allow about 30 `offer_requests` per minute. The defaults are `OUTBOUND_RATE_PER_S=0.4` and burst 4. On a 429, the client waits for `ratelimit-reset` and retries.
- **`duffel_mapper.py`** converts raw offers into the frozen Pydantic models in `domain/offers.py`. Things to know:
  - **Technical stops**: the same flight lands en route, as BR67 does in BKK. They come from `segment.stops`. `FlightOffer.is_nonstop` is false when one is present.
  - **Codeshares**: the mapper reads `operating_carrier`.
  - **Simulated data**: `is_simulated` is `live_mode is False`.
  - **Excluded airlines**: `EXCLUDED_AIRLINES` filters them out (default `ZZ`, Duffel Airways test data).

### Search and explore

`services/search_service.py`:

- `RouteQuery` is a normalized query. Multi-city trips put legs after the first in `extra_legs`.
- It uses cache-aside: the key is `route:{o}:{d}:{dep}:{ret}:{cabin}:{pax_hash}[:mc:…]:{namespace}`, with a 30-minute TTL.

`services/explore_service.py` then processes each search in this order:

1. Run the search.
2. Convert prices to the requested currency with `services/fx.py`.
3. Apply the topology filter from `domain/topology.py`.
4. Rank results with `domain/metrics.py` (cost index and tags).

It also returns `price_bounds` and `duration_bounds`, which drive the frontend sliders.

The fare matrix streams NDJSON:

- The first line holds the axes, the currency, and the `fx_approximate` flag.
- Each later line is one cell.

### FX

- Rates come from open.er-api.com and are cached under `fx:usd` for 6 hours.
- If the fetch fails, the service falls back to a built-in table and marks the result `fx_approximate`.
- `time_value_per_hour` is always entered in USD and converted on the server.

### Watchlists and patrol

`services/patrol.py`, run by the worker or by `POST /api/patrol/run`:

- It is system-wide: it patrols every user's active watches, not just the caller's.
- It first expires watches 1 hour before takeoff (`domain/departure.py`). The takeoff time is the first leg of the latest `price_history.offers`, read in the origin airport's timezone. A watch with no recorded flight expires when the departure date ends at the origin.
- It groups the remaining watches by `(query, key_fingerprint)`, consumes the groups from an asyncio queue, and writes rows to `price_history`.
- Each `price_history` row also stores the chosen offers as JSON (`offers`, one per leg for split tickets). `GET /api/watchlists/{id}/itinerary` returns the latest one for the board's flight-detail panel; older rows without it return `null`.
- Alerts are in `services/alerts.py` and have a 24-hour cooldown.
- A Redis lock (`skyroute:lock:patrol`) ensures only one patrol runs at a time.
- User Duffel keys are stored Fernet-encrypted in `tracked_watchlists.duffel_token_enc`. The encryption key is derived from `SECRET_KEY`.

### Airports and multi-leg watches

- **Airports** (`services/airport_service.py`): one data file, `data/airports.json`, with one airport per line.
  - It holds about 4,000 scheduled-service airports from OurAirports. Update it with `scripts/build_airports.py <airports.csv>`.
  - `size_rank: 0` rows are hand-curated: city codes, timezones, and metro groups like `TYO` and `BJS`. The build script never overwrites them. It also keeps existing `name_zh`, `timezone`, and `city_code` values.
  - Edit `name_zh` directly in the file to add Chinese names.
  - Search matches the accent-folded `search_text`.
  - When nothing matches locally, `/api/airports` asks Duffel `/places/suggestions` and stores the results. Misses are cached for a day.
  - Tests call `seed_airports(..., include_world=False)`, which seeds only the curated rows, for speed.
- **Multi-leg watches**:
  - `ticket_mode="ticket"` is one Duffel query; it can include `extra_legs` for multi-city.
  - `ticket_mode="split"` makes one one-way query per leg, with optional `leg_airlines`, and records the summed price as `airline_code` like `CZ+BR`.
  - The patrol fetches every distinct query first (`FetchResults`), then prices each watch in `evaluate`.
  - Split legs must connect in time (`domain/connections.py`, mirrored in `src/lib/splitPlan.ts`). A leg must depart at least 2h after the previous arrival at the same airport, or 4h when changing airports. `cheapest_chain` picks the cheapest feasible combination with dynamic programming. The patrol and the split view both use it.

### Patrol scheduling

The worker ticks every 60s and patrols only watches whose `next_check_at` has passed. Intervals are set per watch (`services/schedule.py`): `None` means daily at `PATROL_DAILY_AT`. Intervals under 30 minutes require the user's own Duffel key.

### Google sign-in and accounts

`services/auth.py`, `api/auth.py`. The feature is enabled only when both `GOOGLE_CLIENT_ID` and `SECRET_KEY` are set; otherwise the app stays in anonymous mode (`X-User-Id`).

- The frontend gets a Google ID token from Google Identity Services. `POST /api/auth/google` verifies it against Google's JWKS (aud, iss, exp, `email_verified`) and sets the `skyroute_session` cookie: stateless, HMAC-signed, HttpOnly, SameSite=Lax. Local http dev needs `SESSION_COOKIE_SECURE=false`.
- Watchlist ownership is `user_identifier = "g:<user uuid>"`. When sign-in is enabled, watchlist endpoints require a session and otherwise return 401 with `meta.code = "login_required"`. Signing in moves the browser's anonymous watchlists (`X-User-Id`) into the account.
- Duffel key resolution in `api/deps.py:get_user_token`: the `X-Duffel-Token` header, then the account key (Fernet-encrypted in `users.duffel_token_enc`), then the server default. Changing the account key also rewrites the key on that user's active watches, so patrol follows it.
- The nginx CSP in `deploy/security-headers.conf` allowlists `accounts.google.com/gsi` and `*.googleusercontent.com` (avatars).

### Database schema

There is no Alembic. `db.py` runs `create_all` and then the additive `ALTER` statements in `_ADDITIVE_MIGRATIONS`, all under `pg_advisory_xact_lock`. To add a column, add it to `models.py` and append an `ALTER TABLE … ADD COLUMN IF NOT EXISTS` to `_ADDITIVE_MIGRATIONS`.

### API conventions

- Every JSON response uses the envelope `{success, data, error, meta}`.
- Watchlist endpoints need `X-User-Id`. It is an anonymous ID the frontend generates; there are no accounts.
- Errors are translated via `i18n.py` according to `Accept-Language`.
- Missing or invalid Duffel keys return 401.
- `DELETE /api/watchlists/{id}` soft-cancels a watch. Add `?purge=true` to hard-delete it along with its history and alerts.

### Test fixtures

- `tests/conftest.py` seeds the cache with `TEST_FX`: 1 USD = 30 TWD, 0.8 GBP.
- The default currency is TWD, so tests that check USD amounts must pass `"currency": "USD"`.
- `tests/factories.py` builds minimal raw Duffel offers.

## Frontend architecture (`src/`)

### Routing and state

- **No router.** View and search state live in the URL query string through `lib/searchState.ts`, for example `?view=explore&from=…`.
- **`App.tsx`** switches between the views `home`, `explore`, `matrix`, and `board`.
- **Client preferences** live in `useSyncExternalStore` stores backed by localStorage or sessionStorage. Modules that touch storage at import time must guard with a `hasDom` check, because vitest runs in node.

| Preference | Module               |
| ---------- | -------------------- |
| Language   | `i18n/i18n.ts`       |
| Currency   | `lib/currency.ts`    |
| Duffel key | `lib/credentials.ts` |
| User ID    | `lib/user.ts`        |

- **Server data** goes through TanStack Query. `lib/api.ts` adds the `Accept-Language`, `X-User-Id`, and `X-Duffel-Token` headers.

### i18n

- All UI strings are keys in `i18n/messages.ts`.
- The `zh` and `en` dictionaries must have identical keys; a unit test enforces this.
- Confirm messages use `\n` to separate the title from the description (see `splitMessage`).

### UI primitives (`components/ui/`)

These are shadcn/ui-style components built on Radix and cmdk, styled in `shadcn.css` with project tokens. There is no Tailwind.

| Component       | Built on                              |
| --------------- | ------------------------------------- |
| `Select`        | Radix Select                          |
| `Checkbox`      | Radix Checkbox                        |
| `ConfirmDialog` | Radix AlertDialog, via `useConfirm()` |
| `AirportInput`  | Radix Popover + cmdk Command          |

Don't reintroduce native `<select>`, `<datalist>`, checkboxes, or `confirm()`.

`Sheet` is a native `<dialog showModal>`. It sits in the browser's top layer, so Radix floating content must portal into it. `Sheet` provides `PortalContainerContext`, and the primitives read it through `usePortalContainer()`.

### Styling

- Plain CSS per feature folder.
- Tokens live in `styles/tokens.css`, following `DESIGN.md`.
- Responsive rules are in `styles/adaptive.css`. Check layouts at 320, 375, 768, 1024, 1440, and 1920 px with no horizontal overflow.
- Grid children need `minmax(0, 1fr)` and `min-width: 0`.

## Known stale README note

The README's "設計決策與已知限制" section still says prices are stored in Duffel's currency without conversion. That is outdated: FX conversion is implemented (`services/fx.py`).
