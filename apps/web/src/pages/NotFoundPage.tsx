import { Button } from "@mantine/core";
import { IconCompassOff } from "@tabler/icons-react";
import { Link } from "react-router";

import { EmptyState } from "../components/layout-bits";

export default function NotFoundPage() {
  return (
    <EmptyState icon={<IconCompassOff size={26} />} title="Nothing on this frequency">
      This page doesn't exist.{" "}
      <Button component={Link} to="/" variant="subtle" size="compact-sm">
        Back to the command center
      </Button>
    </EmptyState>
  );
}
