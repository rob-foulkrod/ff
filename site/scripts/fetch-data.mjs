import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Paths relative to the site directory
const REPORTS_DIR = path.resolve(__dirname, '../../reports/weekly');
const OUTPUT_FILE = path.resolve(__dirname, '../src/data/league-data.json');

console.log('🏈 FoulkNFootball Data Pipeline');
console.log('=====================================');

// Parse markdown table into objects
function parseMarkdownTable(content, startMarker, endMarker = null) {
  const lines = content.split('\n');
  let startIndex = -1;
  let endIndex = lines.length;

  // Find start of table - be more specific for overall standings
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(startMarker)) {
      // For standings, make sure it's the main standings, not division standings
      if (startMarker.includes('Standings Through Week')) {
        // Make sure the next few lines don't contain "Division" or "###"
        let isMainStandings = true;
        for (let j = i; j < Math.min(i + 5, lines.length); j++) {
          if (lines[j].includes('Division') || lines[j].startsWith('###')) {
            isMainStandings = false;
            break;
          }
        }
        if (!isMainStandings) continue;
      }
      
      // Look for the actual table header (starts with |)
      for (let j = i; j < lines.length; j++) {
        if (lines[j].trim().startsWith('|') && lines[j].includes('|')) {
          startIndex = j;
          break;
        }
      }
      break;
    }
  }

  if (startIndex === -1) return [];

  // Find end of table (first non-table line or end marker)
  for (let i = startIndex + 1; i < lines.length; i++) {
    if (endMarker && lines[i].includes(endMarker)) {
      endIndex = i;
      break;
    }
    if (!lines[i].trim().startsWith('|') || lines[i].includes('---')) {
      continue;
    }
    // Stop at next section header
    if (lines[i].trim().startsWith('##') || lines[i].trim().startsWith('###')) {
      endIndex = i;
      break;
    }
    if (lines[i].trim() === '' || (!lines[i].includes('|') && lines[i].trim() !== '')) {
      endIndex = i;
      break;
    }
  }

  const tableLines = lines.slice(startIndex, endIndex).filter(line => 
    line.trim().startsWith('|') && !line.includes('---')
  );

  if (tableLines.length < 2) return [];

  // Parse header
  const headers = tableLines[0]
    .split('|')
    .map(h => h.trim())
    .filter(h => h !== '');

  // Parse data rows
  const data = [];
  for (let i = 1; i < tableLines.length; i++) {
    const values = tableLines[i]
      .split('|')
      .map(v => v.trim())
      .filter((v, idx) => idx > 0 && idx <= headers.length); // Skip first empty and limit to header length

    if (values.length >= headers.length - 1) {
      const row = {};
      headers.forEach((header, idx) => {
        const value = values[idx] || '';
        // Convert numeric fields
        if (['W', 'L', 'T', 'rank', 'seed', 'roster_id', 'games'].includes(header)) {
          row[header] = parseInt(value) || 0;
        } else if (['win_pct', 'PF', 'PA'].includes(header)) {
          row[header] = parseFloat(value) || 0;
        } else {
          row[header] = value;
        }
      });
      data.push(row);
    }
  }

  return data;
}

// Extract metadata from report
function parseReportMetadata(content) {
  const metadata = {};
  const metadataMatch = content.match(/## Metadata\n(.*?)\n\n/s);
  
  if (metadataMatch) {
    const metadataLines = metadataMatch[1].split('\n');
    for (const line of metadataLines) {
      if (line.includes('|') && !line.includes('key')) {
        const [key, value] = line.split('|').map(s => s.trim()).filter(s => s);
        if (key && value) {
          metadata[key] = value;
        }
      }
    }
  }
  
  return metadata;
}

// Read all report files and organize by season/week
function readReports() {
  const reports = {};
  
  if (!fs.existsSync(REPORTS_DIR)) {
    console.log('⚠️  Reports directory not found:', REPORTS_DIR);
    return reports;
  }

  console.log('📂 Reports directory found:', REPORTS_DIR);

  // Read years (2024, 2025, etc.)
  const years = fs.readdirSync(REPORTS_DIR, { withFileTypes: true })
    .filter(dirent => dirent.isDirectory())
    .map(dirent => dirent.name);

  console.log(`📁 Found season directories: ${years.join(', ')}`);

  years.forEach(year => {
    const yearPath = path.join(REPORTS_DIR, year);
    console.log(`🔍 Reading year directory: ${yearPath}`);
    
    const weekFiles = fs.readdirSync(yearPath)
      .filter(file => file.startsWith('week-') && file.endsWith('.md'))
      .sort((a, b) => {
        const weekA = parseInt(a.match(/week-(\d+)/)[1]);
        const weekB = parseInt(b.match(/week-(\d+)/)[1]);
        return weekA - weekB;
      });

    console.log(`📊 ${year}: Found ${weekFiles.length} weekly reports - ${weekFiles.join(', ')}`);

    if (!reports[year]) {
      reports[year] = {};
    }

    weekFiles.forEach(file => {
      const weekMatch = file.match(/week-(\d+)/);
      if (weekMatch) {
        const week = weekMatch[1];
        const filePath = path.join(yearPath, file);
        console.log(`📖 Reading ${file} from ${filePath}`);
        
        try {
          const content = fs.readFileSync(filePath, 'utf-8');
          
          // Parse the report data
          const metadata = parseReportMetadata(content);
          const standings = parseMarkdownTable(content, '## Standings Through Week');
          const weeklyResults = parseMarkdownTable(content, '## Weekly Results Week');
          const headToHead = parseMarkdownTable(content, '## Head-to-Head Grid Through Week');
          
          reports[year][week] = {
            content: content,
            metadata: metadata,
            standings: standings,
            weeklyResults: weeklyResults,
            headToHead: headToHead,
            lastModified: fs.statSync(filePath).mtime.toISOString(),
            week: parseInt(week),
            year: parseInt(year)
          };
          
          console.log(`✅ Processed Week ${week} - Standings: ${standings.length}, H2H: ${headToHead.length}`);
        } catch (error) {
          console.error(`❌ Error reading ${file}:`, error.message);
        }
      }
    });
  });

  return reports;
}

// Extract season-end standings from the last week's report
function extractSeasonStandings(reports) {
  const seasons = {};

  for (const [year, yearReports] of Object.entries(reports)) {
    // Get the highest week number (last week of season)
    const weeks = Object.keys(yearReports).map(w => parseInt(w)).sort((a, b) => b - a);
    const lastWeek = weeks[0];
    
    if (lastWeek && yearReports[lastWeek] && yearReports[lastWeek].standings) {
      // Filter to unique teams only (avoid duplicates from division/playoff tables)
      const uniqueTeams = [];
      const seenOwners = new Set();
      
      yearReports[lastWeek].standings.forEach(team => {
        if (team.owner && !seenOwners.has(team.owner) && team.owner !== 'owner') {
          seenOwners.add(team.owner);
          uniqueTeams.push(team);
        }
      });
      
      // Take only first 8 teams (standard league size)
      const finalStandings = uniqueTeams.slice(0, 8);
      
      seasons[year] = {
        standings: finalStandings.map((team, index) => ({
          rank: team.rank || index + 1,
          team: getDisplayName(team.owner),
          wins: team.W,
          losses: team.L,
          ties: team.T || 0,
          points: team.PF,
          pointsAgainst: team.PA,
          winPercentage: parseFloat((team.win_pct * 100).toFixed(1))
        })),
        totalWeeks: weeks.length,
        lastUpdated: yearReports[lastWeek].lastModified
      };
    }
  }

  return seasons;
}

// Helper function to get display name from username
function getDisplayName(username) {
  const nameMap = {
    'robfoulk': 'Rob',
    'jfoulkrod': 'Jake', 
    'Evenkeel75': 'Brian',
    'Dbfoulkrod': 'Devin',
    'asmartaleck1': 'Dave',
    'mafoulk': 'Michael',
    'ebmookie': 'Eric',
    'NOTDoda': 'Dakota'
  };
  return nameMap[username] || username;
}

// Family structure mapping (updated with correct usernames from reports)
function getFamilyStructure() {
  return {
    dads: [
      { name: 'Rob', username: 'robfoulk', role: 'League Veteran' },
      { name: 'Brian', username: 'Evenkeel75', role: 'Strategic Mind' }, 
      { name: 'Dave', username: 'asmartaleck1', role: 'Consistent Performer' },
      { name: 'Eric', username: 'ebmookie', role: 'Wildcard' }
    ],
    sons: [
      { name: 'Jake', username: 'jfoulkrod', dad: 'Rob' },
      { name: 'Devin', username: 'Dbfoulkrod', dad: 'Brian' },
      { name: 'Michael', username: 'mafoulk', dad: 'Dave' },
      { name: 'Dakota', username: 'NOTDoda', dad: 'Eric' }
    ]
  };
}

// Calculate head-to-head records across all weeks
function calculateHeadToHeadRecords(reports) {
  const h2hRecords = {};
  
  for (const [year, yearReports] of Object.entries(reports)) {
    for (const [week, report] of Object.entries(yearReports)) {
      if (report.weeklyResults) {
        report.weeklyResults.forEach(game => {
          // Extract team names and scores from weekly results
          // Format varies, but typically includes team names and scores
          console.log(`Processing H2H for ${year} Week ${week}:`, game);
        });
      }
    }
  }
  
  return h2hRecords;
}

// Main execution
async function main() {
  try {
    console.log('📖 Reading weekly reports...');
    const reports = readReports();
    
    console.log('🏆 Extracting season standings...');
    const seasons = extractSeasonStandings(reports);
    
    console.log('👨‍👦 Setting up family structure...');
    const family = getFamilyStructure();
    
    console.log('⚔️ Calculating head-to-head records...');
    const headToHead = calculateHeadToHeadRecords(reports);
    
    // Combine all data
    const leagueData = {
      seasons,
      reports,
      family,
      headToHead,
      lastUpdated: new Date().toISOString(),
      metadata: {
        totalSeasons: Object.keys(seasons).length,
        totalReports: Object.values(reports).reduce((total, year) => total + Object.keys(year).length, 0),
        generatedBy: 'FoulkNFootball Data Pipeline v2.0',
        dataSource: 'Weekly Markdown Reports + Sleeper API'
      }
    };

    // Ensure output directory exists
    const outputDir = path.dirname(OUTPUT_FILE);
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }

    // Write the consolidated data file
    console.log('💾 Writing league data...');
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(leagueData, null, 2));
    
    console.log('✅ Data pipeline completed successfully!');
    console.log(`📊 Processed: ${leagueData.metadata.totalReports} reports across ${leagueData.metadata.totalSeasons} seasons`);
    
    // Show sample data
    for (const [year, season] of Object.entries(seasons)) {
      console.log(`🏆 ${year} Final Standings:`);
      season.standings.slice(0, 3).forEach(team => {
        console.log(`   ${team.rank}. ${team.team} (${team.wins}-${team.losses}, ${team.winPercentage}%)`);
      });
    }
    
    console.log(`📄 Output: ${OUTPUT_FILE}`);
    console.log('🎯 Ready for Astro site generation!');
    
  } catch (error) {
    console.error('❌ Error in data pipeline:', error);
    process.exit(1);
  }
}

// Run the pipeline
main();
