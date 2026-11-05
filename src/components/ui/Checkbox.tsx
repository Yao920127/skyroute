import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { useId, type ReactNode } from "react";

import "./shadcn.css";

type Props = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
};

/** shadcn/ui Checkbox（Radix Checkbox）＋標籤：取代瀏覽器原生勾選框 */
export function Checkbox({ checked, onCheckedChange, children, disabled }: Props) {
  const id = useId();
  return (
    <div className="sc-checkbox-row">
      <CheckboxPrimitive.Root
        id={id}
        className="sc-checkbox"
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(value === true)}
      >
        <CheckboxPrimitive.Indicator className="sc-checkbox__indicator">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </CheckboxPrimitive.Indicator>
      </CheckboxPrimitive.Root>
      <label htmlFor={id} className="sc-checkbox-label">
        {children}
      </label>
    </div>
  );
}
