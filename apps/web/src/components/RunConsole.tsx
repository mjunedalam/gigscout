import { Box } from "@mantine/core";
import { useEffect, useRef } from "react";

import { utc } from "../lib/format";

interface RunConsoleProps {
  lines: { at?: string; line: string }[];
  height?: number;
  placeholder?: string;
}

/** Streams agent steps like a terminal and keeps the newest line in view. */
export function RunConsole({ lines, height = 300, placeholder = "Waiting for the agents…" }: RunConsoleProps) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" }); // braces: newer browsers return a Promise, not a cleanup
  }, [lines.length]);

  return (
    <Box className="gs-console" h={height} role="log" aria-live="polite">
      {lines.length === 0 && <span style={{ color: "#5d6478" }}>{placeholder}</span>}
      {lines.map((entry, i) => {
        const [who, ...rest] = entry.line.split(":");
        return (
          <div key={i}>
            {entry.at && <span className="gs-console-time">{utc(entry.at).format("HH:mm:ss")}</span>}
            {rest.length ? (
              <>
                <span className="gs-console-who">{who}</span>:{rest.join(":")}
              </>
            ) : (
              entry.line
            )}
          </div>
        );
      })}
      <div ref={end} />
    </Box>
  );
}
