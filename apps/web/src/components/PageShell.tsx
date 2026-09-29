import { AppShell, type AppShellProps } from './AppShell'

export type { NavigationPath } from './Sidebar'
export type PageShellProps = AppShellProps

/**
 * The shell every route uses. Kept as a thin alias of `AppShell` so the routes did not
 * change when the layout moved from a top bar to a sidebar (SPEC 46, F46-02).
 */
export function PageShell(props: PageShellProps) {
  return <AppShell {...props} />
}
