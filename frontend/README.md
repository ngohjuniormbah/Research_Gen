# Research_Gen — frontend

Frontend dédié à **Research_Gen**, sans référence à KG-Chat et sans modification du backend.

## Backend configuré

`https://litreview-web.onrender.com`

La configuration est dans `.env.production` / `.env.example`.

## Fonctionnalités alignées sur le backend

- Création et gestion des clés API (`POST/GET/DELETE /api/v1/auth/api-keys`).
- Chargement dynamique des modèles via `GET /api/v1/models` : aucune liste LLM concurrente n'est codée dans l'interface.
- Upload CSV / XLSX / PDF / JSON via `POST /api/v1/documents`.
- Vérification du statut de parsing avant génération.
- Génération asynchrone via `POST /api/v1/reviews`, `Idempotency-Key`, puis polling `GET /api/v1/reviews/jobs/{job_id}`.
- Affichage de `ReviewOut`, sections, citations, sources, provider, model et usage.
- Preview HTML via `GET /api/v1/reviews/{review_id}/preview?format=html`.
- Exports MD, DOCX et PDF. Le PDF suit le job asynchrone et l'URL signée fournie par le backend.
- Recherche ORKG via `GET /api/v1/orkg/search`.
- Exécution SPARQL via `POST /api/v1/orkg/sparql`, en laissant les garde-fous au backend.
- Connexion ORKG OIDC via `POST /api/v1/orkg/connect`.
- Paramètres de génération correspondant à `ReviewCreate`: `topic`, `instructions`, `provider`, `document_ids`, `orkg_query`, `orkg_size`, `max_tokens`.

## Important

Le frontend ne crée pas de contrat alternatif. Les textes de l'interface utilisent les termes du backend : **documents, sources, revue de littérature, job, provider, modèle, ORKG, SPARQL, preview, export**.

Le backend reste la source de vérité pour :
- les modèles disponibles ;
- la validation ;
- les limites ;
- la normalisation des `SourceRecord` ;
- l'exécution ORKG ;
- la génération et le statut des jobs.

## Lancer

```bash
npm install
npm run dev
```

Build :

```bash
npm run build
```

Aucune clé API de production n'est embarquée dans l'archive.
