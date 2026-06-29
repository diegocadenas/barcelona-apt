# Barcelona Apartment Finder

Hourly scanner for [Habitatge Jove](https://www.habitatgejove.com/webv2c/en/pisos.asp) student flats near Carrer de Provença 216, Barcelona.

## Features

- Filters 3+ bedroom flats within ~30 min walk of school
- Excludes Raval, Ciutat Vella, and L'Hospitalet
- Web dashboard with list + map views and month filters
- Optional hourly scan via macOS `launchd`

## Quick start

```bash
python3 scan_flats.py          # run scan → reports/latest.json
./open_dashboard.sh            # open http://localhost:8765
```

Edit `config.json` to adjust school location, room minimum, or excluded zones.

Edit `config.json` to adjust school location, room minimum, or excluded zones.

## Deploy to Vercel

The dashboard is static. Listing data comes from `reports/latest.json`, updated hourly by GitHub Actions.

1. Push this repo to GitHub (`github.com/diegocadenas/barcelona-apt`).
2. Sign in at [vercel.com](https://vercel.com) with your **personal** GitHub account (not IBM).
3. **Add New Project** → import `diegocadenas/barcelona-apt`.
4. Settings:
   - **Framework Preset:** Other
   - **Build Command:** leave empty
   - **Output Directory:** `.` (root)
   - **Install Command:** leave empty
5. Click **Deploy**.

Your site will be live at something like `https://barcelona-apt.vercel.app`. Each hourly scan commit triggers an automatic redeploy.

Enable GitHub Actions on the repo (Settings → Actions → Allow) so the hourly workflow runs.

## Hourly scan (optional, local Mac)

```bash
cp com.barcelona-apt.daily-scan.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.barcelona-apt.daily-scan.plist
```
