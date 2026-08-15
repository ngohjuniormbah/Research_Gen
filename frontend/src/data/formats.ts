import type { DocumentKind } from '@/types';

// File types the backend can ingest (see the backend's magic-byte `sniff_kind`).
// `.jsonld` (ORKG knowledge-graph exports) is parsed as JSON on the backend.
export const ACCEPT =
  '.csv,.xlsx,.xls,.pdf,.json,.jsonld,' +
  'text/csv,' +
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,' +
  'application/pdf,application/json,application/ld+json';

const LABELS: Record<DocumentKind, string> = {
  csv: 'CSV',
  xlsx: 'Excel',
  pdf: 'PDF',
  json: 'JSON',
  unknown: 'Fichier',
};

/** Human-readable label for a document kind (used in the document list). */
export function formatLabel(kind: string): string {
  return LABELS[kind as DocumentKind] ?? 'Fichier';
}

/** Best-effort file kind from a filename extension (mirrors the backend families). */
export function guessKind(filename: string): DocumentKind {
  const ext = filename.toLowerCase().split('.').pop() ?? '';
  if (ext === 'csv') return 'csv';
  if (ext === 'xlsx' || ext === 'xls') return 'xlsx';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'json' || ext === 'jsonld') return 'json';
  return 'unknown';
}
