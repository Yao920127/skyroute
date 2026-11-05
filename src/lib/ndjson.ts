/** 把累積的文字切成完整的行；最後一段不完整的文字原樣留給下一次。 */
export function splitLines(buffer: string): { lines: string[]; rest: string } {
  const parts = buffer.split("\n");
  const rest = parts.pop() ?? "";
  return { lines: parts.map((p) => p.trim()).filter(Boolean), rest };
}

/** 逐行解析 NDJSON 串流。 */
export async function* readNdjson<T>(stream: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const { lines, rest } = splitLines(buffer + decoder.decode(value, { stream: true }));
    buffer = rest;
    for (const line of lines) yield JSON.parse(line) as T;
  }
  if (buffer.trim()) yield JSON.parse(buffer) as T;
}
