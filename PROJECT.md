# My Sports project specification

## Purpose
Personal sports dashboard designed primarily for Alex's Samsung Galaxy Z Fold.

## Teams
- Tottenham Hotspur, SofaScore team ID `33`
- Bath Rugby, SofaScore team ID `4196`
- England football, SofaScore team ID `4713`
- England rugby, SofaScore team ID `4226`

## Current behaviour
Each team card shows:
- team badge
- team name and sport
- latest completed fixture
- latest score
- competition
- next fixture
- UK date and kick-off time

## Interactions
- tapping a team header opens that team's SofaScore page
- tapping a previous result opens that exact SofaScore event
- tapping a next fixture opens that exact SofaScore event
- the app checks its own hosted `data.json` every 5 minutes while open
- GitHub Actions refreshes the source data automatically
- refresh when the app returns to the foreground
- manual Refresh button
- last successful data is retained locally as fallback if the live feed is temporarily unavailable

## Design
- dark interface
- rounded cards
- compact mobile-first layout
- responsive on a Galaxy Z Fold
- preserve the current visual style unless Alex explicitly asks for a redesign

## Data source
The installed app reads `data.json` from its own GitHub Pages origin. A GitHub Actions updater fetches fixture and result data from ESPN public schedule endpoints on a recurring basis. This avoids browser CORS restrictions. Team headers continue to open SofaScore. Match cards use the exact event URL supplied by the active data source.

## Deployment
Installable Progressive Web App hosted with GitHub Pages from this repository.

## Maintenance instructions for future ChatGPT sessions
This repository is the source of truth. Before changing the app:
1. Read this file.
2. Read the current `index.html`, `manifest.webmanifest` and `service-worker.js`.
3. Preserve existing functionality unless the user explicitly asks to change it.
4. Update this document if product behaviour or team coverage changes.
