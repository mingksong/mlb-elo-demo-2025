/**
 * Team logo SVG imports — maps team abbreviation to logo asset.
 */

const logoModules = import.meta.glob('../assets/logos/*.svg', { eager: true, query: '?url', import: 'default' });

const teamLogos: Record<string, string> = {};

for (const [path, url] of Object.entries(logoModules)) {
  // path: "../assets/logos/nyy.svg" → key: "NYY"
  const match = path.match(/\/([^/]+)\.svg$/);
  if (match) {
    teamLogos[match[1].toUpperCase()] = url as string;
  }
}

/**
 * Get the logo URL for a team abbreviation.
 * Returns undefined if no logo exists for that team.
 */
export function getTeamLogoUrl(team: string): string | undefined {
  return teamLogos[team.toUpperCase()];
}
