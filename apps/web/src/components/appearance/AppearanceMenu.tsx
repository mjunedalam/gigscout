import {
  ActionIcon,
  type MantineColorScheme,
  Popover,
  SegmentedControl,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { IconCheck, IconDeviceDesktop, IconMoon, IconPalette, IconSun } from "@tabler/icons-react";
import { type MouseEvent, useRef } from "react";
import { flushSync } from "react-dom";

import { ACCENTS, type AccentName, useAppearance } from "../../app/appearance-context";
import { DARK_SHADE } from "../../app/accents";
import { prefersReducedMotion } from "../../lib/motion/gsap";

type ViewTransitionDocument = Document & { startViewTransition?: (update: () => void) => { ready: Promise<void> } };

/**
 * Swap the theme behind a circle that grows from where the viewer clicked (View Transitions API). Browsers without
 * it, and viewers who prefer less motion, get an instant switch.
 */
function withThemeReveal(event: MouseEvent, apply: () => void) {
  const doc = document as ViewTransitionDocument;
  if (!doc.startViewTransition || prefersReducedMotion()) {
    apply();
    return;
  }
  const x = event.clientX || window.innerWidth - 40;
  const y = event.clientY || 30;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  const transition = doc.startViewTransition(() => flushSync(apply));
  transition.ready
    .then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 520, easing: "cubic-bezier(0.16, 1, 0.3, 1)", pseudoElement: "::view-transition-new(root)" },
      );
    })
    .catch(() => {
      /* the transition was skipped (e.g. tab hidden); the theme already applied */
    });
}

const SCHEMES = [
  { value: "light", label: "Light", icon: IconSun },
  { value: "dark", label: "Dark", icon: IconMoon },
  { value: "auto", label: "System", icon: IconDeviceDesktop },
] as const;

export function AppearanceMenu() {
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("dark");
  const { accent, setAccent } = useAppearance();
  const lastClick = useRef<MouseEvent | null>(null);

  return (
    <Popover position="bottom-end" width={260} shadow="lg" radius="lg" withArrow>
      <Popover.Target>
        <Tooltip label="Appearance">
          <ActionIcon size={36} aria-label="Appearance: theme and accent colour">
            {computed === "dark" ? <IconMoon size={18} /> : <IconSun size={18} />}
          </ActionIcon>
        </Tooltip>
      </Popover.Target>
      <Popover.Dropdown p="md">
        <Stack gap="md">
          <Stack gap={8}>
            <span className="gs-eyebrow">Theme</span>
            <SegmentedControl
              fullWidth
              size="xs"
              radius="xl"
              value={colorScheme}
              onMouseDown={(e) => { lastClick.current = e; }}
              onChange={(value) => {
                const apply = () => setColorScheme(value as MantineColorScheme);
                if (lastClick.current) withThemeReveal(lastClick.current, apply);
                else apply();
              }}
              data={SCHEMES.map((s) => ({
                value: s.value,
                label: (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    <s.icon size={14} />
                    {s.label}
                  </span>
                ),
              }))}
            />
          </Stack>
          <Stack gap={8}>
            <span className="gs-eyebrow">
              <IconPalette size={12} style={{ verticalAlign: "-2px", marginRight: 6 }} />
              Accent
            </span>
            <div className="gs-swatches" role="radiogroup" aria-label="Accent colour">
              {(Object.keys(ACCENTS) as AccentName[]).map((name) => (
                <Tooltip key={name} label={ACCENTS[name].label}>
                  <UnstyledButton
                    role="radio"
                    aria-checked={accent === name}
                    aria-label={ACCENTS[name].label}
                    className="gs-swatch gs-focus"
                    style={{ "--swatch": ACCENTS[name].scale[DARK_SHADE] } as never}
                    onClick={() => setAccent(name)}
                  >
                    {accent === name && <IconCheck size={14} stroke={3} />}
                  </UnstyledButton>
                </Tooltip>
              ))}
            </div>
            <Text size="xs" c="var(--gs-text-muted)">
              The accent marks what is live, healthy or qualified.
            </Text>
          </Stack>
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
