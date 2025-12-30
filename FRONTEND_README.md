# Draft Day Frontend - Quick Start Guide

## Overview

A React-based frontend for real-time fantasy baseball draft decision support. Displays 4 core panels:
1. **Available Players** - Sortable/filterable list with personal vs. market value
2. **Projected Standings** - Final standings if draft ended now
3. **League Resources** - Budget and roster competition
4. **Team Needs** - Strategic recommendations ranked by ease of improvement

## Running the System

### Production Mode (Recommended)

Frontend is built and served by the FastAPI server:

```bash
# Start the API server (serves frontend at http://localhost:8000/)
python -m src.draft.run_api_server
```

Navigate to http://localhost:8000/ in your browser.

### Development Mode (Hot Reload)

Run frontend dev server with API proxy:

```bash
# Terminal 1: Start API server
python -m src.draft.run_api_server

# Terminal 2: Start Vite dev server
cd frontend
npm run dev
```

Navigate to http://localhost:5173/ (Vite dev server with hot reload).

## Configuration

### User Team ID

Edit `src/config.py`:

```python
USER_TEAM_ID = 'team_01'  # Change to match your team
```

The frontend will highlight your team in standings and calculate recommendations specifically for you.

### Auto-Refresh Interval

Edit `src/config.py`:

```python
FRONTEND_AUTO_REFRESH_INTERVAL = 10  # seconds
```

Default: 10 seconds. Set to 0 to disable auto-refresh (manual only).

## API Endpoints

The frontend consumes these endpoints:

- `GET /draft-session/results` - Player valuations and team summary
- `GET /draft-session/standings` - Projected final standings
- `GET /draft-session/competition` - League-wide resource tracking
- `GET /draft-session/team-needs` - Strategic recommendations
- `GET /draft-session/config` - Frontend configuration

## Building the Frontend

To rebuild after making changes:

```bash
cd frontend
npm run build
```

Output goes to `../dist/` which is served by FastAPI.

## Customization

### Changing Refresh Behavior

Edit `frontend/src/App.tsx`:

```typescript
<DraftProvider autoRefreshInterval={10000}>  // milliseconds
```

### Filtering Available Players

Default filters in Available Players Panel:
- Position filter (all positions available)
- Minimum personal value filter
- Limit to top 100 players displayed

### Panel Layout

Grid layout is defined in `frontend/src/App.css`:
- Desktop (>1400px): 2-column grid
- Mobile (<1400px): Single column

Available Players and Team Needs panels span full width in both layouts.

## Troubleshooting

### Frontend shows "No active session"

You need to start a draft session first via the API:

```bash
curl -X POST http://localhost:8000/draft-session/start \
  -H "Content-Type: application/json" \
  -d '{"league_id": "YOUR_LEAGUE_ID", "season": 2026}'
```

### Frontend not updating

1. Check that the API server is running
2. Verify the draft session is active (not paused)
3. Check browser console for errors
4. Manual refresh button forces immediate update

### "dist directory not found" warning

Frontend hasn't been built yet:

```bash
cd frontend
npm install
npm run build
```

## Tech Stack

- **React 18** with TypeScript
- **Vite** build tool
- **Axios** for API calls
- **CSS Modules** for styling
- **FastAPI** static file serving

## Performance

- Auto-refresh uses parallel API calls (all endpoints fetched simultaneously)
- Players panel limits display to top 100 by default
- Expandable category breakdowns load on demand
- Production build uses code splitting and minification
