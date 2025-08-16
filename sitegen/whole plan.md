# FoulkNFootball History Site - Structure Plan

## Site Overview
A multi-year fantasy football league history site showcasing stats, recaps, and rivalries for the FoulkNFootball (FFF) league - a family league with deep generational rivalries.

## Site Structure

### 1. **Home/Landing Page**
- **Hero Section**
  - Current season spotlight (2025)
  - Latest week's top performer
  - Current league leader
  - Countdown to next matchup
- **Quick Stats Dashboard**
  - Current season standings mini-table
  - Active streaks
  - This week's matchups preview
- **Latest Recap** (excerpt with "Read More")
- **Family Tree Visual** (interactive showing Dads vs Sons rivalries)
- **Navigation to all seasons**

### 2. **Seasons Hub** `/seasons`
- **Season Selector** (dropdown or cards)
  - 2025 (Current - Featured)
  - 2024 (Complete)
  - Historic seasons (2014-2023) - "Coming Soon" placeholders
- **Season Summary Cards** showing:
  - Champion
  - Runner-up
  - Top scorer
  - Biggest upset
  - Key rivalries settled

### 3. **Season Pages** `/seasons/{year}`
- **Season Overview**
  - Final standings
  - Playoff bracket
  - Season records (highest score, biggest blowout, etc.)
  - Champion spotlight
- **Week Navigation** (1-17 including playoffs)
- **Season-Long Stats**
  - Head-to-head grid (full season)
  - Power rankings chart over time
  - Division standings progression

### 4. **Weekly Pages** `/seasons/{year}/week/{number}`
- **AI-Generated Recap** (from Recap.Instructions.md style)
  - Dramatic headline
  - Game-by-game narratives
  - Rivalry spotlights
- **Raw Data Sections** (from week-XX.md)
  - Standings through this week
  - Weekly results with details
  - Head-to-head records
  - Streaks tracker
- **Preview Next Week** (if available)
- **Historical Context** (comparison to previous seasons)

### 5. **Rivalries Page** `/rivalries`
- **All-Time Head-to-Head Records**
  - Interactive grid showing historical matchups
  - Filter by: Dad vs Son, Twin vs Twin, Cousins, etc.
- **Rivalry Spotlights**
  - Rob vs Jake (Father vs Son)
  - Brian vs Dave (Twin Battle)
  - Dave vs His Sons (Michael & Dakota)
  - Eric vs The Brothers
- **Rivalry Stats**
  - Biggest blowouts
  - Closest games
  - Season sweeps
  - Playoff eliminations

### 6. **Hall of Records** `/records`
- **Single Game Records**
  - Highest score
  - Lowest score
  - Biggest victory margin
  - Most points in a loss
- **Season Records**
  - Best record
  - Most points scored
  - Longest win streak
  - Perfect weeks
- **All-Time Records**
  - Championships won
  - Playoff appearances
  - Career win percentage
  - Total points scored

### 7. **Teams/Owners Page** `/teams`
- **Owner Profiles** (one for each of the 8)
  - All-time record
  - Championships
  - Best/worst seasons
  - Nemesis (most losses to)
  - Favorite victim (most wins against)
  - Trophy case (awards, records held)
- **Team History**
  - Season-by-season results
  - Playoff history
  - Notable trades/moves

### 8. **Playoffs Central** `/playoffs`
- **Current Year Bracket** (if in playoffs)
- **Historical Brackets**
- **Playoff Statistics**
  - Most appearances
  - Championship game records
  - Upset history
- **Road to the Championship** (year by year)

### 9. **Power Rankings** `/power`
- **Current Week Power Rankings**
- **Power Rankings History** (week by week chart)
- **All-Time Power Rankings**
- **"What If" Rankings** (strength of schedule adjusted)

### 10. **The Recap Archive** `/recaps`
- **Searchable/Filterable List**
  - By season
  - By week  
  - By team involved
  - By rivalry type
- **Best of Recaps**
  - Most dramatic finishes
  - Biggest upsets
  - Championship weeks
  - Rivalry week specials

## Navigation Structure
```
Primary Nav:
- Home
- 2025 Season (Featured)
- Past Seasons ▼
  - 2024
  - Archive (2014-2023)
- Rivalries
- Records
- Teams

Secondary Nav (Context-sensitive):
- When viewing a season: Week 1-17 quick jump
- When viewing a week: Previous Week | Next Week
- When viewing team: Season selector
```

## Key Features
1. **Mobile-First Responsive Design**
2. **Dark/Light Mode Toggle** (for late-night score checking)
3. **Quick Stats Hover Cards** (hover over any team name for mini stats)
4. **Shareable URLs** for specific weeks/matchups
5. **RSS/JSON Feed** for latest recaps
6. **Search Functionality** (teams, weeks, specific matchups)

## Technical Implementation Notes
- Static site generation from Sleeper API data
- Markdown weekly reports as data source
- AI recap generation pipeline
- GitHub Pages or Netlify hosting
- Updates via GitHub Actions (automated weekly)

## Future Enhancements
- Draft history and analysis
- Trade tracker
- Injury impact analysis  
- "What if" playoff scenarios
- Prediction engine for upcoming weeks
- Integration with previous 10 years of data when available

## Data Sources
- **Sleeper API**: https://api.sleeper.com/v1/
  - League ID: 1180276953741729792 (2025)
  - Previous League ID: 1112858215559057408 (2024)
- **Weekly Reports**: Generated markdown files (week-XX.md)
- **AI Recaps**: Generated from Recap.Instructions.md template

## Family & League Context
### Dads (three brothers + cousin)
- **Rob** (`robfoulk`) – oldest brother  
- **Brian** (`Evenkeel75`) – twin  
- **Dave** (`asmartaleck1`) – twin  
- **Eric** (`ebmookie`) – cousin  

### Sons
- **Jake** (`jfoulkrod`) – Rob's son  
- **Devin** (`Dbfoulkrod`) – Brian's son  
- **Michael** (`mafoulk`) – Dave's son  
- **Dakota** (`NOTDoda`) – Dave's son  

This structure provides a comprehensive yet navigable experience that celebrates the league's history while keeping current season action front and center. The family rivalry aspect is woven throughout, making it more than just stats - it's a story of family competition.