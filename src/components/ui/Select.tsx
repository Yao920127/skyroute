import * as SelectPrimitive from "@radix-ui/react-select";
import type { ReactNode } from "react";

import "./shadcn.css";
import { usePortalContainer } from "./portal.ts";

export type SelectOption = {
  value: string;
  label: ReactNode;
  description?: string;
  disabled?: boolean;
};

type Props = {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  ariaLabel: string;
  size?: "sm" | "md";
  className?: string;
  id?: string;
};

const Chevron = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="sc-icon">
    <path d="m6 9 6 6 6-6" />
  </svg>
);

const Check = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="sc-icon">
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

/** shadcn/ui Select（Radix Select）：取代瀏覽器原生 <select> 下拉選單 */
export function Select({
  value,
  onValueChange,
  options,
  ariaLabel,
  size = "md",
  className,
  id,
}: Props) {
  const container = usePortalContainer();
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        id={id}
        className={`sc-select-trigger sc-select-trigger--${size} ${className ?? ""}`}
        aria-label={ariaLabel}
      >
        <SelectPrimitive.Value />
        <SelectPrimitive.Icon asChild>
          <Chevron />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal container={container}>
        <SelectPrimitive.Content
          className="sc-popover sc-select-content"
          position="popper"
          sideOffset={6}
        >
          <SelectPrimitive.Viewport className="sc-select-viewport">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                disabled={option.disabled}
                className="sc-select-item"
              >
                <span className="sc-select-item__indicator">
                  <SelectPrimitive.ItemIndicator>
                    <Check />
                  </SelectPrimitive.ItemIndicator>
                </span>
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                {option.description && (
                  <span className="sc-select-item__desc">{option.description}</span>
                )}
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
