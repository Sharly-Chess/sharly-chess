**[Retour au sommaire de la documentation](../README.md)**

# Papi-web - Annexe technique : Distribution du logiciel

## Génération d'un exécutable pour Windows

Papi-web est fourni aux utilisateur·ices finaux·ales sous la forme d'une archive contenant un exécutable pour simplifier son utilisation par des arbitres non-informaticien·nes.

Le script `/scripts/export/export.py` :
- crée le fichier `/export/papi-web-x.y.z.zip` utilisé pour distribuer le logiciel ;
- crée un environnement dans `/export-test` permettant des tests fonctionnels hors environnement de développement.

> [!NOTE]
> Des exports Linux devront être envisagés lorsque l'adhérence à Access aura été supprimée.

## Publication des versions

Règles (non-immuables) adoptées :

- Un seul patch d'une version mineure est conservée dans les _releases_ en ligne sur GitHub
