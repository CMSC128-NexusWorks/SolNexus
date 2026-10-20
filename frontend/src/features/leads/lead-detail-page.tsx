import { ArrowLeftIcon } from "lucide-react";
import { Link, useParams } from "react-router";

import { TicketPlaceholder } from "@/components/ticket-placeholder";
import { Button } from "@/components/ui/button";

import { useLeadHistory } from "./queries";

// Lead detail with interaction history (wireframe 04).
export function LeadDetailPage() {
  const { clinicId } = useParams();
  const history = useLeadHistory(clinicId);

  return (
    <div className="flex flex-col gap-6">
      <Button variant="link" className="self-start px-0" asChild>
        <Link to="/">
          <ArrowLeftIcon data-icon="inline-start" />
          All clinics
        </Link>
      </Button>
      {/* TODO(SNX-59): replace with the lead record panel and interaction history. */}
      <TicketPlaceholder
        ticket="SNX-59"
        title="Lead detail and interaction history"
        wireframe="04 · Lead detail — interaction history.png"
      >
        <p className="text-sm text-muted-foreground">
          {history.data
            ? `${history.data.items.length} interactions loaded for clinic ${clinicId}`
            : "Loading history…"}
        </p>
      </TicketPlaceholder>
    </div>
  );
}
