# YouTube 2.0 : règles du dépôt

- Le dépôt GitHub `youtube-aura-farming-2` (remote `aura`, suivi par `main`) est **public** : jamais de clé, de mot de
  passe, d'adresse e-mail personnelle ni de vidéo d'un autre créateur. Les clés vivent dans les `.env` (ignorés par
  git) ou chiffrées en base ; `examples/` reste sur le PC.
- La CI (`.github/workflows/ci.yml`) rejoue à chaque push : worker → `ruff check`, `ruff format --check`, `pytest` ;
  dashboard → `npm ci`, `npm run lint`, `tsc --noEmit`, `npm run build`. Avant de commiter du Python, passer
  `ruff format --check` et appliquer ce qu'il demande (`ruff format --diff` montre les changements) ; après un
  changement de dépendances du dashboard, commiter le `package-lock.json` tenu à jour par `npm install`.
