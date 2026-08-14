@echo off
echo CwHUB Render deploy helper
where git >nul 2>nul || echo Git topilmadi. Avval Git o'rnating.
echo 1) GitHub repositoryga push qiling.
echo 2) Render'da Blueprint sifatida render.yaml ni ulang.
echo 3) ADMIN_PASSWORD ni secret sifatida kiriting.
echo 4) Deploy tugagach /healthz ni tekshiring.
pause
