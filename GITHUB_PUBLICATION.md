# Publish the audited TripParadox source to a PUBLIC GitHub repository

**Publication status as of 18 Nov 2026:** NOT PUBLISHED. We verified the authenticated GitHub username `swarnojit`, but the current GitHub connector has zero accessible installations/repositories and exposes no repository-creation action. **Do not copy an assumed repository URL into submissions.** Only share the URL printed and verified after the instructions below complete.

## Recommended: GitHub CLI

1. Install Git and [GitHub CLI](https://cli.github.com/) on your trusted laptop.
2. Extract the complete project ZIP and open a terminal **in its project root** (the folder containing `README.md`, `.gitignore` and `docker-compose.yml`).
3. Authenticate: `gh auth login` (your `swarnojit` account, with repository creation permission).
4. Run the checked helper: `bash scripts/publish_public_github.sh TripParadox-Security-Lab`.
5. The helper creates a new public repository, pushes `main`, requests repo metadata and prints the actual public URL. Verify it in a signed-out browser, and only then insert it in the report.

The helper scans for prohibited source filenames and verifies `.env` is Git-ignored. **It is not a comprehensive secret scanner.** Before making any code public, use GitHub's secret scanning / push protection or run `gitleaks` locally and check every staged file. Do not publish supplier credentials, real customer records, `.env`, databases, backup files, local tokens or confidential hackathon materials.

## Alternative: GitHub website

Open [GitHub New Repository](https://github.com/new) when signed in, choose owner `swarnojit`, repository name `TripParadox-Security-Lab`, visibility **Public**, and do **not** initialize the repo with a generated README. Then in the extracted project root:

```bash
git init -b main
git add .
git status --short          # confirm no .env, DB, backups or secrets
git commit -m "Publish TripParadox synthetic security lab and technical report"
git remote add origin https://github.com/swarnojit/TripParadox-Security-Lab.git
git push -u origin main
```

**Important:** The URL above is a command argument for a repository you still must create. It is **not** a verified public link. Do not cite it until the push and an unauthenticated page-open check succeed.

## Afterwards: report link update

Replace `GitHub publication: NOT YET PUBLISHED` in `docs/COMPREHENSIVE_SECURITY_TECHNICAL_REPORT.md` with `Public source repository: <the verified URL>`. Edit the Word/PDF report accordingly and commit the final version. Confirm `README.md`, the report, `backend/app` and the GitHub Actions workflow render in the public repository. CI success is a useful check, but not a production security certification.
