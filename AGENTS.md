## Start

Web (filters, title table, pagination) and the SnailJob executor are two processes in this repo. Start both with:

```bash
./scripts/start.sh
```

If web or the executor is already running (pid file, port 8000 / 17889, or matching command), the script leaves it alone and only starts the missing process.

Stop or check:

```bash
./scripts/start.sh stop
./scripts/start.sh status
```

Open the admin page at http://127.0.0.1:8000 (needs `web/dist`; run `npm --prefix web run build` if the page is missing). Logs are `log/web.log` and `log/snailjob.log`.

Do not start SnailJob server with this script. That is Docker compose at `/Users/conchi/docker-compose/snail-job`. Admin: http://127.0.0.1:18080/snail-job. Vite on 5173 is optional frontend hot reload, not required for this start path.

Scheduled crawl is two jobs, same executor `watchSieveRefresh`: LINUX DO every 15 minutes (`configs/linux_do.yaml`); V2EX at minute 8 and 38 (`configs/v2ex.yaml`) so they do not share the refresh lock. Manual page refresh still uses `configs/sites.yaml` (both sites).

Scheduled LLM judge is a third job on the same Python executor process, name `watchSieveJudge`. It classifies pending titles then watch-filters pending titles; it does not take the crawl lock. Cron minutes 5, 20, 35, 50 so it does not overlap V2EX at :08/:38. Create the job in SnailJob admin; Python only registers the function. Opening 分类 or 关注 does not call the model.

## UI work

- Read the root `DESIGN.md` before making a material UI change.
- If `DESIGN.md` is missing or the requested change replaces the visual direction, use the UI Design Advisor skill to inspect the project, compare three references, and propose a project-owned design system before implementation.
- Use one primary reference. A secondary reference may contribute only an explicitly named pattern.
- Treat the root `DESIGN.md` as the visual source of truth; update it before introducing new colors, typography, spacing, radii, elevation, or component rules.
- Keep a full-width top menu (`标题` `/` · `分类` `/topics` · `关注` `/watch`). The title list is still four filters, a title table, and pagination. 分类 is a separate page with its own rail, filters, and columns. Add a menu item only when that page exists.
- Reuse existing primitives and preserve product behavior unless a broader change is explicitly requested.
- Do not copy third-party logos, brand copy, proprietary fonts, signature imagery, or a complete brand identity.
- Verify at 375px, 768px, and 1440px. Check focus, contrast, 200% zoom, reduced motion, loading, empty, and error states.
- Test long Chinese titles; do not ellipsize them.
