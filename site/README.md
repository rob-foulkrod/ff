# Foulk ’n Football 🏈

A comprehensive fantasy football league website showcasing over a decade of family competition, built with modern web technologies.

## 🎯 Project Overview

Foulk ’n Football is a static website that chronicles the ongoing fantasy football saga between two generations - the Dads vs the Sons. This project combines automated data collection from the Sleeper fantasy football platform with a beautiful, responsive web interface built using Astro and React.

## �️ Tech Stack

- **Frontend**: Astro 5.x with React components
- **Styling**: Tailwind CSS for responsive design
- **Data Source**: Sleeper API integration
- **Report Generation**: Python scripts with markdown output
- **Deployment**: GitHub Actions (planned)
- **Content**: Markdown-based weekly reports

## 🚀 Project Structure

Inside the FoulkNFootball project, you'll see the following structure:

```text
ff/
├── site/                           # Astro website (this directory)
│   ├── src/
│   │   ├── components/
│   │   │   ├── FamilyTree.tsx      # Family rivalry visualization
│   │   │   └── StandingsTable.tsx  # Responsive standings display
│   │   ├── layouts/
│   │   │   └── BaseLayout.astro    # Main site layout
│   │   ├── pages/
│   │   │   ├── index.astro         # Homepage with current standings
│   │   │   ├── rivalries.astro     # Head-to-head records
│   │   │   ├── records.astro       # All-time achievements
│   │   │   ├── teams.astro         # Owner profiles
│   │   │   └── seasons/
│   │   │       ├── index.astro     # Season browser
│   │   │       ├── [year].astro    # Individual season pages
│   │   │       └── [year]/week/[week].astro # Weekly report pages
│   │   └── data/
│   │       └── league-data.json    # Processed league data
│   ├── scripts/
│   │   └── fetch-data.mjs          # Data pipeline from Python to web
│   └── package.json
├── scripts/                        # Python data processing
│   ├── weekly_report.py            # Main report generator
│   ├── validate_sleeper_api.py     # API validation
│   └── lib/                        # Core libraries
├── reports/weekly/2024/            # Generated markdown reports
└── requirements.txt                # Python dependencies
```

## 🎨 Features

### 🏆 Current Features

- **Responsive Homepage**: Current standings and league overview
- **Season Browser**: Navigate through all seasons with timeline view
- **Weekly Reports**: Detailed markdown reports with statistics
- **Family Rivalries**: Dads vs Sons head-to-head tracking
- **All-Time Records**: Championships, season records, and quirky stats
- **Team Profiles**: Complete owner information and achievements
- **Dark Mode**: Full dark/light theme support
- **Mobile Responsive**: Optimized for all screen sizes

### 🚧 Planned Features

- **AI-Powered Recaps**: GPT-generated weekly summaries with personality insights
- **Interactive Charts**: D3.js visualizations for trends and statistics
- **Playoff Bracket**: Dynamic tournament visualization

## 🧞 Commands

All commands are run from the root of this project directory, from a terminal:

| Command                   | Action                                           |
| :------------------------ | :----------------------------------------------- |
| `npm install`             | Installs dependencies                            |
| `npm run dev`             | Starts local dev server at `localhost:4321`      |
| `npm run build`           | Build your production site to `./dist/`          |
| `npm run preview`         | Preview your build locally, before deploying     |
| `npm run fetch-data`      | Update league data from Python reports          |
| `npm run astro ...`       | Run CLI commands like `astro add`, `astro check` |
| `npm run astro -- --help` | Get help using the Astro CLI                     |

## 🎭 Family Rivalry Theme

The site centers around the ongoing battle between generations:

### 👨 The Dads
- Rob Foulk (`robfoulk`) - League veteran and championship contender
- Brian Battles (`bbattles2`) - Strategic mastermind
- Dave Koz (`DaveKoz`) - Consistent performer
- Eric K (`Eric_K`) - Wildcard with surprising upsets

### � The Sons  
- Jake Foulk (`jfoulkrod`) - Rising star and defending champion
- Devin Battles (`devinbattles`) - Young gun with championship aspirations
- Michael Koz (`michaelkoz`) - Future potential waiting to be unlocked
- Dakota Knutson (`dakotadknutson`) - The underdog story in progress

## 📊 Data Pipeline

The project uses a sophisticated data pipeline:

1. **Python Scripts** (in parent directory) fetch data from Sleeper API
2. **Markdown Reports** are generated with statistics and narratives
3. **Node.js Script** (`scripts/fetch-data.mjs`) processes reports into JSON
4. **Astro Site** renders static pages with dynamic React components

## 🚀 Development Workflow

```bash
# 1. Generate reports (run from parent directory)
cd .. && python scripts/weekly_report.py

# 2. Fetch fresh data for website
npm run fetch-data

# 3. Start development server
npm run dev
```

## 🏈 League Information

- **2024 Season**: League ID `1112858215559057408` (Complete)
- **2025 Season**: League ID `1180276953741729792` (Current)
- **Family Structure**: 4 Dads vs 4 Sons

## �👀 Want to learn more?

Feel free to check [our documentation](https://docs.astro.build) or jump into our [Discord server](https://astro.build/chat).

---

**Built with ❤️ by the Foulk ’n Football family**

*Where family bonds meet fantasy football competition!*
