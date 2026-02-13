#!/bin/bash
# =============================================================================
# Script de reconstruction du repo de production Flatpak
#
# Ce script supprime l'historique OSTree existant dans repo/ sur gh-pages,
# puis déclenche des builds pour chaque version taguée afin de recréer
# un historique de production propre.
#
# Prérequis :
#   - GitHub CLI (gh) installé et authentifié
#   - Accès push sur la branche gh-pages du fork
#
# Usage :
#   bash scripts/rebuild_production_repo.sh [--dry-run]
# =============================================================================

set -euo pipefail

REPO="GillesHorn/sharly-chess"
WORKFLOW="publish-multiarch.yml"
BRANCH="linux-flatpak"
PRODUCTION_VERSIONS=("3.5.0" "3.5.1" "3.5.2")

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "=== MODE DRY-RUN (aucune action réelle) ==="
fi

echo ""
echo "=== Étape 1 : Nettoyage du repo de production sur gh-pages ==="
echo ""

TMPDIR=$(mktemp -d)
echo "Clonage de gh-pages dans $TMPDIR..."

if [ "$DRY_RUN" = false ]; then
  git clone --branch gh-pages --single-branch "https://github.com/${REPO}.git" "$TMPDIR/ghpages"
  cd "$TMPDIR/ghpages"

  if [ -d "repo" ]; then
    echo "Suppression du répertoire repo/ (ancien historique mixte)..."
    rm -rf repo
    git add -A
    git commit -m "Reset production repo for clean rebuild"
    git push origin gh-pages
    echo "✓ repo/ supprimé et poussé sur gh-pages"
  else
    echo "repo/ n'existe pas encore, rien à supprimer"
  fi

  cd -
  rm -rf "$TMPDIR"
else
  echo "[dry-run] Supprimerait repo/ sur gh-pages"
fi

echo ""
echo "=== Étape 2 : Reconstruction des versions de production ==="
echo ""
echo "Déclenchement des builds pour : ${PRODUCTION_VERSIONS[*]}"
echo ""

for VERSION in "${PRODUCTION_VERSIONS[@]}"; do
  echo "→ Build de la version $VERSION..."
  if [ "$DRY_RUN" = false ]; then
    gh workflow run "$WORKFLOW" \
      --repo "$REPO" \
      --ref "$BRANCH" \
      --field "version_tag=$VERSION"

    echo "  ✓ Workflow déclenché pour $VERSION"
    echo "  ⏳ Attente de 30s avant le prochain build (éviter les conflits gh-pages)..."
    sleep 30
  else
    echo "  [dry-run] gh workflow run $WORKFLOW --repo $REPO --ref $BRANCH --field version_tag=$VERSION"
  fi
done

echo ""
echo "=== Terminé ==="
echo ""
echo "Les builds sont en cours sur GitHub Actions."
echo "Vérifiez l'avancement : https://github.com/${REPO}/actions/workflows/${WORKFLOW}"
echo ""
echo "⚠️  Chaque build prend environ 15-20 minutes."
echo "⚠️  Les versions apparaîtront dans le repo de production dans l'ordre de complétion."
echo "    Le sommaire OSTree est recalculé à chaque build, donc l'ordre final sera correct."
