import { ConstructionIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

interface TicketPlaceholderProps {
  ticket: string;
  title: string;
  wireframe: string;
  children?: ReactNode;
}

/**
 * Marks a screen section that a Jira ticket will build. Delete it when the ticket lands.
 */
export function TicketPlaceholder({ ticket, title, wireframe, children }: TicketPlaceholderProps) {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ConstructionIcon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>
          Built in <Badge variant="secondary">{ticket}</Badge> · see{" "}
          <code className="font-mono text-xs">docs/wireframes/{wireframe}</code>
        </EmptyDescription>
      </EmptyHeader>
      {children && <EmptyContent>{children}</EmptyContent>}
    </Empty>
  );
}
