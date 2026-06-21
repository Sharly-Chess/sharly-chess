# Proposition : génération des tableaux Molter

Ce dossier regroupe une proposition à la Direction Nationale de
l'Arbitrage : **construire et vérifier les tableaux Molter par programme**,
plutôt que de maintenir des tableaux fixes recopiés à la main (qui
accumulent des coquilles — joueur en double, coéquipiers appariés,
déséquilibre de couleurs).

## Contenu

| Fichier | Rôle |
|---------|------|
| `molter-developer-guide.md` | Guide développeur (anglais) : explication pas à pas du code de génération, pour les mainteneurs sans bagage mathématique. À lire en premier. |
| `molter-specification.md` | Spécification autonome et indépendante du langage (anglais) : de quoi reproduire les tableaux dans n'importe quel langage, ou valider une implémentation tierce. |
| `molter_standalone.py` | Script **autonome** (bibliothèque standard Python uniquement, aucune dépendance) : génère et vérifie un tableau. |
| `build_xlsx.py` | Construit le classeur Excel des tableaux complets à partir du script autonome (nécessite `xlsxwriter`) ; option `--summary` pour ajouter une feuille de synthèse des critères. |

Les classeurs Excel ne sont pas versionnés : ils se régénèrent avec
`build_xlsx.py` (option `--summary`).

## Utilisation du script autonome

```sh
# un tableau précis (5 équipes, 10 joueurs) :
python3 molter_standalone.py 5 10

# imposer le nombre de rondes régulières :
python3 molter_standalone.py 9 8 --rounds 2

# toute la grille (3-13 équipes × 4,6,8,10,12 joueurs), export CSV :
python3 molter_standalone.py --grid --csv tableaux.csv
```

Chaque tableau produit est **vérifié** contre les principes Molter (y
compris les règles de flotteurs S6a/S6b/S6c et de couleurs — équilibre par
joueur, pas de triplement, doublement seulement au passage pair→impair)
avant d'être affiché. La
génération est **déterministe et portable, sans aléa** (la seule recherche est un
petit backtracking déterministe et borné pour le choix des arêtes flotteur) : la
liste des échiquiers se construit par couches de `N − 1`
échiquiers, chacune réalisant un `K_N` complet (facteurs one-odd à `N`
impair, 1-factorisation à `N` pair). Quand `N − 1` divise `P`, on atteint
I1 à chaque ronde ; sinon une dernière couche partielle couvre le reste, en
restant valide. La configuration `(équipes, joueurs, rondes)` définit donc un
unique tableau, reproductible à l'identique dans n'importe quel langage (il
n'y a pas de germe à transmettre). Le CSV est l'export sans dépendance ;
`build_xlsx.py` produit la version Excel équivalente.
