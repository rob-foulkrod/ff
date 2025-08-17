import React from 'react';

interface StandingsProps {
  standings: Array<{
    team: string;
    wins: number;
    losses: number;
    ties?: number;
    pointsFor: number;
    pointsAgainst?: number;
    rosterId: number;
  }>;
}

const StandingsTable: React.FC<StandingsProps> = ({ standings }) => {
  const calculateWinPct = (wins: number, losses: number, ties: number = 0) => {
    const totalGames = wins + losses + ties;
    if (totalGames === 0) return 0;
    return ((wins + ties * 0.5) / totalGames);
  };

  return (
    <>
      <div className="text-center text-sm text-gray-600 dark:text-gray-400 mb-4">
        <strong>Note:</strong> The league's only official divisions are <strong>Kids Table 1985</strong> and <strong>Kids Table 2010</strong>.<br />
      </div>
      <div className="overflow-x-auto">
      <table className="min-w-full bg-white dark:bg-gray-800 rounded-lg shadow">
        <thead className="bg-green-700 text-white">
          <tr>
            <th className="px-4 py-3 text-left">Rank</th>
            <th className="px-4 py-3 text-left">Team</th>
            <th className="px-4 py-3 text-center">Record</th>
            <th className="px-4 py-3 text-center">Win %</th>
            <th className="px-4 py-3 text-right">Points For</th>
            <th className="px-4 py-3 text-right">Points Against</th>
          </tr>
        </thead>
        <tbody>
          {standings.map((team, index) => {
            const winPct = calculateWinPct(team.wins, team.losses, team.ties);
            const record = team.ties ? `${team.wins}-${team.losses}-${team.ties}` : `${team.wins}-${team.losses}`;
            
            return (
              <tr key={team.rosterId} className="border-b dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                <td className="px-4 py-3 font-bold text-lg">{index + 1}</td>
                <td className="px-4 py-3 font-semibold">{team.team}</td>
                <td className="px-4 py-3 text-center font-mono">{record}</td>
                <td className="px-4 py-3 text-center">{(winPct * 100).toFixed(1)}%</td>
                <td className="px-4 py-3 text-right font-mono">{team.pointsFor.toFixed(2)}</td>
                <td className="px-4 py-3 text-right font-mono">{team.pointsAgainst?.toFixed(2) || '0.00'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
};

export default StandingsTable;
