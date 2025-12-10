---
description: Workflow global pour valider, synchroniser et gérer les versions Git (Semantic Versioning)
---

# Workflow Git Release

Ce workflow guide les opérations de validation, synchronisation et gestion des versions.
**L'IA génère automatiquement les messages de commit et les numéros de version.**

---

## 1. Valider le code (Tests) - *Optionnel*

> Cette étape est recommandée mais peut être ignorée si vous êtes confiant dans vos changements.

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; python -m pytest mail2rag/tests -v ; python -m pytest ragproxy/tests -v
```

> ⚠️ **Si exécuté, ne pas continuer si les tests échouent.**

---

## 2. Vérifier le statut Git

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git status
```

---

## 3. Synchroniser avec le dépôt distant

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git fetch origin ; git pull origin main
```

> Résoudre les conflits si nécessaire avant de continuer.

---

## 4. Analyser les changements et générer le message

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git diff --stat ; git diff
```

**L'IA doit :**
1. Analyser le `git diff` pour comprendre les changements
2. Générer un message de commit au format Conventional Commits :
   - `feat:` nouvelle fonctionnalité → incrémente MINOR
   - `fix:` correction de bug → incrémente PATCH
   - `feat!:` ou `BREAKING CHANGE:` → incrémente MAJOR
   - `docs:`, `chore:`, `refactor:`, `test:` → pas d'incrément de version
3. Proposer le message au USER pour validation

---

## 5. Ajouter et commiter les changements

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git add -A ; git commit -m "<MESSAGE_GÉNÉRÉ>"
```

> Remplacer `<MESSAGE_GÉNÉRÉ>` par le message proposé par l'IA.

---

## 6. Incrémenter la version (Semantic Versioning)

**L'IA doit :**
1. Lire la version actuelle dans `mail2rag/version.py`
2. Calculer la nouvelle version selon le type de commit :
   - **MAJOR** (breaking change) : `X.0.0`
   - **MINOR** (feat) : `x.Y.0`
   - **PATCH** (fix) : `x.y.Z`
3. Modifier `mail2rag/version.py` avec la nouvelle version
4. Commiter avec : `chore: bump version to X.Y.Z`

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git add mail2rag/version.py ; git commit -m "chore: bump version to X.Y.Z"
```

---

## 7. Créer un tag Git

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

> L'IA remplace automatiquement `X.Y.Z` par la nouvelle version.

---

## 8. Pousser vers le dépôt distant

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git push origin main ; git push origin --tags
```

---

## Résumé du workflow automatisé

| Étape | Action | Automatisation IA |
|-------|--------|-------------------|
| 1 | pytest | Exécution auto |
| 2 | git status | Exécution auto |
| 3 | git fetch/pull | Exécution auto |
| 4 | git diff | Analyse + génération message |
| 5 | git commit | Message auto-généré |
| 6 | version.py | Calcul + modification auto |
| 7 | git tag | Version auto |
| 8 | git push | Exécution |
