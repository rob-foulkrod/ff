import React from 'react';

interface FamilyMember {
  name: string;
  username: string;
  role?: string;
  dad?: string;
}

interface FamilyTreeProps {
  familyTree?: {
    dads: FamilyMember[];
    sons: FamilyMember[];
  };
}

const FamilyTree: React.FC<FamilyTreeProps> = ({ familyTree }) => {
  const families = familyTree || {
    dads: [
      { name: 'Rob', username: 'robfoulk', role: 'Oldest Brother' },
      { name: 'Brian', username: 'Evenkeel75', role: 'Twin' },
      { name: 'Dave', username: 'asmartaleck1', role: 'Twin' },
      { name: 'Eric', username: 'ebmookie', role: 'Cousin' }
    ],
    sons: [
      { name: 'Jake', username: 'jfoulkrod', dad: 'Rob' },
      { name: 'Devin', username: 'Dbfoulkrod', dad: 'Brian' },
      { name: 'Michael', username: 'mafoulk', dad: 'Dave' },
      { name: 'Dakota', username: 'NOTDoda', dad: 'Dave' }
    ]
  };

  return (
    <div className="grid md:grid-cols-2 gap-8">
      {/* Dads Column */}
      <div className="bg-blue-50 dark:bg-blue-900/20 p-6 rounded-lg border-2 border-blue-200 dark:border-blue-700">
        <h3 className="text-2xl font-bold mb-4 text-blue-800 dark:text-blue-300 flex items-center">
          👨‍🦳 The Dads
        </h3>
        <div className="space-y-3">
          {families.dads.map(dad => (
            <div key={dad.username} className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md border border-blue-100 dark:border-blue-800">
              <p className="font-bold text-lg">{dad.name}</p>
              <p className="text-sm text-gray-600 dark:text-gray-400 font-mono">@{dad.username}</p>
              <p className="text-xs text-blue-600 dark:text-blue-400 font-semibold">{dad.role}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Sons Column */}
      <div className="bg-green-50 dark:bg-green-900/20 p-6 rounded-lg border-2 border-green-200 dark:border-green-700">
        <h3 className="text-2xl font-bold mb-4 text-green-800 dark:text-green-300 flex items-center">
          👨‍💼 The Sons
        </h3>
        <div className="space-y-3">
          {families.sons.map(son => (
            <div key={son.username} className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md border border-green-100 dark:border-green-800">
              <p className="font-bold text-lg">{son.name}</p>
              <p className="text-sm text-gray-600 dark:text-gray-400 font-mono">@{son.username}</p>
              <p className="text-xs text-green-600 dark:text-green-400 font-semibold">{son.dad}'s son</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default FamilyTree;
