---
description: Workflow global pour valider, synchroniser et gérer les versions Git (Semantic Versioning)
---

# Workflow Git Release

Ce workflow guide les opérations de validation, synchronisation et gestion des versions.
**L'IA génère automatiquement les messages de commit et les numéros de version.**

## Modes disponibles

| Mode | Commande | Description |
|------|----------|-------------|
| **Standard** | `/git-release` | Commit + version bump + tag + push |
| **Rapide** | `/git-release quick` | Commit + push (sans version ni tag) |
| **Avec tests** | `/git-release avec tests` | Exécute pytest avant le workflow |

---

## 0. Vérifier la branche active

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git branch --show-current
```

**L'IA doit :**
- Vérifier que la branche est `main`
- Si autre branche : demander confirmation avant de continuer
- Proposer de basculer sur `main` si nécessaire

---

## 1. Valider le code (Tests) - *Désactivé par défaut*

> ⏭️ **Cette étape est ignorée par défaut.** Pour l'activer : `/git-release avec tests`

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; python -m pytest mail2rag/tests -v ; python -m pytest ragproxy/tests -v
```

---

## 2. Vérifier le statut Git

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git status --short
```

---

## 3. Synchroniser avec le dépôt distant

// turbo
```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git fetch origin ; git pull origin main
```

> ⚠️ Si conflits détectés, l'IA doit arrêter et aider à les résoudre.

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

---

## 6. Incrémenter la version (Semantic Versioning)

> ⏭️ **Mode "quick" : cette étape est ignorée.**

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

> ⏭️ **Mode "quick" : cette étape est ignorée.**

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

---

## 8. Confirmation avant push

**L'IA doit demander confirmation :**

> 🚀 **Prêt à pousser vers GitHub !**
>
> - Commit(s) : `<liste des commits>`
> - Tag : `vX.Y.Z` (si mode standard)
> - Branche : `main`
>
> **Confirmer le push ? (oui/non)**

---

## 9. Pousser vers le dépôt distant

```powershell
cd d:\SynologyDrive\Antigravity\Mail2Rag ; git push origin main ; git push origin --tags
```

---

## 🔙 Rollback en cas de problème

Si quelque chose ne va pas après le push, voici comment annuler :

### Annuler le dernier commit (pas encore pushé)
```powershell
git reset --soft HEAD~1
```

### Annuler le dernier commit (déjà pushé)
```powershell
git revert HEAD
git push origin main
```

### Supprimer un tag local
```powershell
git tag -d vX.Y.Z
```

### Supprimer un tag distant
```powershell
git push origin --delete vX.Y.Z
```

### Revenir à un commit spécifique
```powershell
git log --oneline -5  # Voir les derniers commits
git reset --hard <commit_hash>
git push origin main --force  # ⚠️ Dangereux, écrase l'historique
```

---

## Résumé du workflow

| Étape | Action | Standard | Quick |
|-------|--------|----------|-------|
| 0 | Vérifier branche | ✅ | ✅ |
| 1 | pytest | ⏭️ Optionnel | ⏭️ Optionnel |
| 2 | git status | ✅ | ✅ |
| 3 | git fetch/pull | ✅ | ✅ |
| 4 | git diff + analyse | ✅ | ✅ |
| 5 | git commit | ✅ | ✅ |
| 6 | version bump | ✅ | ⏭️ |
| 7 | git tag | ✅ | ⏭️ |
| 8 | Confirmation | ✅ | ✅ |
| 9 | git push | ✅ | ✅ |
