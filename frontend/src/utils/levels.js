export const LEVEL_LABELS = {
  fonds:      'Fonds',
  series:     'Série',
  subseries:  'Sous-série',
  recordgrp:  'Groupe',
  subgrp:     'Sous-fonds',
  file:       'Dossier',
  item:       'Pièce',
  otherlevel: '',
}

export function levelLabel(l) {
  return LEVEL_LABELS[l] || l || ''
}
