import { getTeamLogoUrl } from '../../utils/teamLogos';

interface TeamLogoProps {
  team: string;
  size?: number;
  className?: string;
}

/**
 * Displays team logo SVG, falling back to team abbreviation text.
 */
export default function TeamLogo({ team, size = 40, className = '' }: TeamLogoProps) {
  const logoUrl = getTeamLogoUrl(team);

  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={team}
        width={size}
        height={size}
        className={`object-contain ${className}`}
      />
    );
  }

  return (
    <span className={`text-xs font-bold text-gray-600 ${className}`}>{team}</span>
  );
}
