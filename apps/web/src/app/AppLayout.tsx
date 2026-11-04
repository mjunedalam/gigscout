import {
  ActionIcon,
  AppShell,
  Avatar,
  Badge,
  Burger,
  Divider,
  Group,
  Kbd,
  Menu,
  NavLink,
  ScrollArea,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useHotkeys, useLocalStorage, useMediaQuery } from "@mantine/hooks";
import { Spotlight, type SpotlightActionData, spotlight } from "@mantine/spotlight";
import {
  IconAdjustmentsHorizontal,
  IconAddressBook,
  IconBolt,
  IconBuildingFactory2,
  IconBuildingStore,
  IconCalendarTime,
  IconChartHistogram,
  IconClipboardList,
  IconHeartRateMonitor,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconLogout,
  IconMessageQuestion,
  IconMoon,
  IconPlugConnected,
  IconRadar2,
  IconSearch,
  IconShieldLock,
  IconSun,
  IconUsers,
  IconSettings,
  IconCreditCard,
} from "@tabler/icons-react";
import type { ReactNode } from "react";
import { NavLink as RouterLink, Outlet, useLocation, useNavigate } from "react-router";

import { useAuth } from "../lib/auth";
import { BillingBanner } from "../components/workspace/BillingBanner";
import { WorkspaceSwitcher } from "../components/workspace/WorkspaceSwitcher";
import { useLive } from "../lib/live";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  description: string;
}

const WORKSPACE: NavItem[] = [
  { to: "/cockpit", label: "Agent cockpit", icon: <IconBuildingFactory2 size={18} />, description: "Watch the agents work, live" },
  { to: "/", label: "Command center", icon: <IconRadar2 size={18} />, description: "Live metrics, galaxy, activity" },
  { to: "/leads", label: "Leads", icon: <IconAddressBook size={18} />, description: "Table and pipeline board" },
  { to: "/analytics", label: "Analytics", icon: <IconChartHistogram size={18} />, description: "Scores, competition, funnel" },
  { to: "/ask", label: "Ask", icon: <IconMessageQuestion size={18} />, description: "Question your lead memory" },
];

const OPERATIONS: NavItem[] = [
  { to: "/runs", label: "Runs", icon: <IconBolt size={18} />, description: "Start agents, watch them live" },
  { to: "/schedules", label: "Schedules", icon: <IconCalendarTime size={18} />, description: "Automate runs with cron" },
  { to: "/profiles", label: "Company profiles", icon: <IconBuildingStore size={18} />, description: "What you sell" },
];

const ADMIN: NavItem[] = [
  { to: "/admin/workspace", label: "Workspace", icon: <IconSettings size={18} />, description: "Name, website form, daily digest" },
  { to: "/admin/users", label: "Team", icon: <IconUsers size={18} />, description: "Members and roles in this workspace" },
  { to: "/admin/billing", label: "Billing", icon: <IconCreditCard size={18} />, description: "Plan, usage and payment" },
  { to: "/admin/sources", label: "Connectors", icon: <IconPlugConnected size={18} />, description: "Websites the agents search" },
  { to: "/admin/audit", label: "Audit log", icon: <IconClipboardList size={18} />, description: "Who changed what" },
];

const PLATFORM: NavItem[] = [
  { to: "/admin", label: "System", icon: <IconHeartRateMonitor size={18} />, description: "Health and capacity" },
  { to: "/admin/settings", label: "Configuration", icon: <IconAdjustmentsHorizontal size={18} />, description: "Running config" },
];

const NAV_WIDTH = 248;
const NAV_RAIL_WIDTH = 72;

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure();
  // desktop only: the sidebar can fold to an icon rail (remembered); the mobile drawer always shows labels
  const [navCollapsed, setNavCollapsed] = useLocalStorage({ key: "gs-nav-collapsed", defaultValue: false });
  const isDesktop = useMediaQuery("(min-width: 62em)") ?? false;
  const rail = navCollapsed && isDesktop;
  const toggleRail = () => setNavCollapsed((c) => !c);
  useHotkeys([["mod+B", toggleRail]]);
  const { user, isAdmin, isPlatformAdmin, workspace, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const sections: [string, NavItem[]][] = [
    ["Workspace", WORKSPACE],
    ["Operations", OPERATIONS],
    ...(isAdmin ? ([["Admin", ADMIN]] as [string, NavItem[]][]) : []),
    ...(isPlatformAdmin ? ([["Platform", PLATFORM]] as [string, NavItem[]][]) : []),
  ];
  const actions: SpotlightActionData[] = sections.flatMap(([group, items]) =>
    items.map((item) => ({
      id: item.to,
      label: item.label,
      description: item.description,
      group,
      leftSection: item.icon,
      onClick: () => navigate(item.to),
    })),
  );

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: rail ? NAV_RAIL_WIDTH : NAV_WIDTH, breakpoint: "md", collapsed: { mobile: !opened } }}
      padding={{ base: "md", md: "xl" }}
      styles={{
        main: { background: "transparent" },
        header: { background: "color-mix(in srgb, var(--gs-bg) 82%, transparent)", backdropFilter: "blur(10px)", borderColor: "var(--gs-line)" },
        navbar: { background: "var(--gs-bg-raised)", borderColor: "var(--gs-line)" },
      }}
    >
      <AppShell.Header px="md">
        <Group h="100%" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" aria-label="Toggle navigation" />
            <Brand />
            <WorkspaceSwitcher />
          </Group>
          <Group gap="xs" wrap="nowrap">
            <UnstyledButton onClick={spotlight.open} className="gs-panel gs-focus" px="sm" py={6} visibleFrom="sm" aria-label="Search pages">
              <Group gap="xs" wrap="nowrap">
                <IconSearch size={15} />
                <Text size="sm" c="var(--gs-text-muted)">
                  Jump to…
                </Text>
                <Kbd size="xs">⌘K</Kbd>
              </Group>
            </UnstyledButton>
            <LiveIndicator />
            <ThemeToggle />
            <Menu position="bottom-end" width={220}>
              <Menu.Target>
                <UnstyledButton aria-label="Account menu" className="gs-focus" style={{ borderRadius: 999 }}>
                  <Avatar color="signal" radius="xl" size={34}>
                    {user?.name.slice(0, 2).toUpperCase()}
                  </Avatar>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  <Text size="sm" fw={600} c="var(--gs-text)">
                    {user?.name}
                  </Text>
                  <Text size="xs">{user?.email}</Text>
                </Menu.Label>
                {workspace && (
                  <Menu.Item leftSection={<IconShieldLock size={16} />}>
                    {isPlatformAdmin ? "Platform admin" : `${workspace.role[0]!.toUpperCase()}${workspace.role.slice(1)}`} · {workspace.name}
                  </Menu.Item>
                )}
                <Menu.Divider />
                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={16} />}
                  onClick={async () => {
                    await logout();
                    navigate("/login");
                  }}
                >
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" style={{ transition: "width var(--gs-normal) var(--gs-ease)" }}>
        <AppShell.Section grow component={ScrollArea} type="never">
          <Stack gap="lg" py="xs">
            {sections.map(([title, items]) => (
              <Stack key={title} gap={2}>
                {rail ? <Divider mx="xs" mb={4} /> : (
                  <Text className="gs-eyebrow" px="sm" pb={4}>
                    {title}
                  </Text>
                )}
                {items.map((item) => (
                  <Tooltip key={item.to} label={item.label} position="right" withArrow disabled={!rail}>
                    <NavLink
                      component={RouterLink}
                      to={item.to}
                      end={item.to === "/" || item.to === "/admin"}
                      label={rail ? undefined : item.label}
                      aria-label={item.label}
                      leftSection={item.icon}
                      onClick={close}
                      active={item.to === "/" || item.to === "/admin" ? location.pathname === item.to : location.pathname.startsWith(item.to)}
                      styles={{
                        root: { borderRadius: 10, justifyContent: rail ? "center" : undefined },
                        section: rail ? { marginInlineEnd: 0 } : undefined,
                        label: { fontWeight: 500 },
                      }}
                      color="signal"
                      variant="light"
                    />
                  </Tooltip>
                ))}
              </Stack>
            ))}
          </Stack>
        </AppShell.Section>
        <AppShell.Section visibleFrom="md" pt="xs" style={{ borderTop: "1px solid var(--gs-line)" }}>
          <Tooltip label={rail ? "Expand sidebar (⌘B)" : "Collapse sidebar (⌘B)"} position="right" withArrow>
            <NavLink
              component="button"
              onClick={toggleRail}
              aria-label={rail ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!rail}
              label={rail ? undefined : "Collapse"}
              leftSection={rail ? <IconLayoutSidebarLeftExpand size={18} /> : <IconLayoutSidebarLeftCollapse size={18} />}
              styles={{
                root: { borderRadius: 10, justifyContent: rail ? "center" : undefined, color: "var(--gs-text-muted)" },
                section: rail ? { marginInlineEnd: 0 } : undefined,
              }}
            />
          </Tooltip>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <div style={{ maxWidth: 1480, margin: "0 auto" }}>
          <BillingBanner />
          <Outlet />
        </div>
      </AppShell.Main>

      <Spotlight
        actions={actions}
        nothingFound="No page matches"
        highlightQuery
        shortcut={["mod + K", "/"]}
        searchProps={{ leftSection: <IconSearch size={18} />, placeholder: "Go to…" }}
      />
    </AppShell>
  );
}

function Brand() {
  return (
    <Group gap={10} wrap="nowrap">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <circle cx="14" cy="14" r="7" fill="none" stroke="var(--gs-signal)" strokeWidth="3" />
        <path d="M19 19l6 6" stroke="var(--gs-signal)" strokeWidth="3" strokeLinecap="round" />
        <circle cx="14" cy="14" r="2" fill="var(--gs-inbound)" />
      </svg>
      <Text className="gs-display" fw={600} fz={19}>
        GigScout
      </Text>
      <Badge size="xs" variant="outline" color="gray" visibleFrom="xs">
        agency
      </Badge>
    </Group>
  );
}

function LiveIndicator() {
  const { connection } = useLive();
  const label = connection === "open" ? "Live" : connection === "connecting" ? "Connecting" : "Offline";
  return (
    <Tooltip label={connection === "open" ? "Receiving live updates" : "Live updates paused; reconnecting"}>
      <Group gap={8} px="sm" py={6} className="gs-panel" wrap="nowrap" style={{ borderRadius: 999 }}>
        <span
          className={connection === "open" ? "gs-live-dot" : undefined}
          style={connection === "open" ? undefined : { width: 8, height: 8, borderRadius: 8, background: "var(--gs-text-muted)" }}
        />
        <Text size="xs" className="gs-mono" visibleFrom="xs">
          {label}
        </Text>
      </Group>
    </Tooltip>
  );
}

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("dark");
  const next = scheme === "dark" ? "light" : "dark";
  return (
    <Tooltip label={`Switch to ${next} theme`}>
      <ActionIcon size={36} onClick={() => setColorScheme(next)} aria-label={`Switch to ${next} theme`}>
        {scheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}
