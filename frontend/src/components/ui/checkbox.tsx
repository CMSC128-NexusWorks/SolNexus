import type { ComponentProps } from "react";
import { Checkbox as CheckboxPrimitive } from "radix-ui";
import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/** Radix checkbox follows the existing shadcn component system and remains keyboard operable. */
export function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return <CheckboxPrimitive.Root className={cn("size-4 shrink-0 rounded border border-input data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground focus-visible:outline focus-visible:outline-ring", className)} {...props}>
    <CheckboxPrimitive.Indicator><CheckIcon className="size-3.5" /></CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>;
}
