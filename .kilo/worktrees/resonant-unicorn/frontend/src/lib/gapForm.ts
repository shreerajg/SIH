/**
 * Declaration form definitions for the pre-compliance analyzer.
 *
 * Keys match the attribute names the backend's requirement check-rules read, and
 * the evidence presets match the evidence_type / match_keywords pairs in
 * data/requirements/*.json.
 */

export interface AttributeField {
  key: string
  label: string
  type: 'number' | 'text' | 'boolean' | 'select'
  unit?: string
  options?: string[]
  help?: string
}

export interface EvidencePreset {
  evidence_type: string
  name: string
}

/**
 * Lower-priority technical declarations. These are still sent to the rule
 * engine unchanged when filled in — they are only *hidden by default* in the
 * UI, behind "Show more technical details", so the first ask stays short.
 * Safety-critical devices, classes and materials are deliberately NOT here.
 */
export const ADVANCED_ATTRIBUTE_KEYS = new Set<string>([
  'body_thickness_mm',
  'base_thickness_mm',
  'max_water_temperature_c',
  'earth_continuity_ohm',
  'insulation_resistance_mohm',
  'inner_container_material',
  'anode_inspection_interval_months',
  'supply_cord_csa_mm2',
  'cord_length_mm',
  'toy_materials',
  'liner_density_kg_m3',
  'peripheral_vision_deg',
  'visor_transmittance_percent',
  'voltage_v',
  'power_w',
])

export function isAdvancedField(key: string): boolean {
  return ADVANCED_ATTRIBUTE_KEYS.has(key)
}

/** Simple, human-facing groupings for the evidence checklist. Every preset is
 *  placed by its evidence_type; anything unmapped falls into "Other evidence".
 *  Grouping is presentational only — the selected names sent to the backend,
 *  and therefore the matching, are unchanged. */
export interface EvidenceGroupDef {
  key: string
  label: string
  hint: string
  types: string[]
}

export const EVIDENCE_GROUP_DEFS: EvidenceGroupDef[] = [
  { key: 'test', label: 'Test reports', hint: 'Hydrostatic, safety-device, temperature, endurance, impact…', types: ['test_report'] },
  { key: 'material', label: 'Material / batch certificate', hint: 'Material grade or batch certificates', types: ['material_certificate'] },
  { key: 'technical', label: 'Product design / technical document', hint: 'Construction file, instruction manual, design records', types: ['document'] },
  { key: 'marking', label: 'Marking / label evidence', hint: 'Rating label and marking artwork', types: ['marking_artwork'] },
]

export interface EvidenceGroup extends EvidenceGroupDef {
  items: EvidencePreset[]
}

export function groupEvidence(presets: EvidencePreset[]): EvidenceGroup[] {
  const used = new Set<string>()
  const groups: EvidenceGroup[] = EVIDENCE_GROUP_DEFS.map((def) => {
    const items = presets.filter((p) => def.types.includes(p.evidence_type))
    items.forEach((i) => used.add(i.name))
    return { ...def, items }
  }).filter((g) => g.items.length > 0)

  const other = presets.filter((p) => !used.has(p.name))
  if (other.length > 0) {
    groups.push({ key: 'other', label: 'Other evidence', hint: 'Anything else you can provide', types: [], items: other })
  }
  return groups
}

interface CategoryForm {
  attributes: AttributeField[]
  evidence: EvidencePreset[]
}

const COMMON_EVIDENCE: EvidencePreset[] = [
  { evidence_type: 'marking_artwork', name: 'Rating label / marking artwork (all required markings)' },
  { evidence_type: 'document', name: 'Instruction manual (English + Hindi)' },
  { evidence_type: 'document', name: 'Technical construction file' },
  { evidence_type: 'test_report', name: 'Marking durability (rub) test report' },
]

export const GAP_FORMS: Record<string, CategoryForm> = {
  'water-heater': {
    attributes: [
      { key: 'max_water_temperature_c', label: 'Maximum stored water temperature', type: 'number', unit: '°C', help: 'Clause 5.1.1 limits this.' },
      { key: 'thermal_cutout_fitted', label: 'Thermal cut-out fitted', type: 'boolean' },
      { key: 'thermal_cutout_reset_type', label: 'Thermal cut-out reset type', type: 'select', options: ['manual', 'tool', 'automatic'] },
      { key: 'earthing_terminal_provided', label: 'Dedicated earthing terminal', type: 'boolean' },
      { key: 'earth_continuity_ohm', label: 'Measured earth continuity', type: 'number', unit: 'Ω' },
      { key: 'insulation_resistance_mohm', label: 'Insulation resistance', type: 'number', unit: 'MΩ' },
      { key: 'pressure_relief_device_fitted', label: 'Pressure relief device fitted', type: 'boolean' },
      { key: 'inner_container_material', label: 'Inner container material', type: 'text' },
      { key: 'anode_inspection_interval_months', label: 'Anode inspection interval', type: 'number', unit: 'months' },
      { key: 'protection_class', label: 'Protection class', type: 'select', options: ['I', 'II'] },
      { key: 'supply_cord_csa_mm2', label: 'Supply cord cross-section', type: 'number', unit: 'mm²' },
    ],
    evidence: [
      { evidence_type: 'test_report', name: 'Temperature rise test report' },
      { evidence_type: 'test_report', name: 'Hydrostatic pressure test report' },
      { evidence_type: 'test_report', name: 'Insulation resistance and electric strength test report' },
      { evidence_type: 'test_report', name: 'Earth continuity test report' },
      { evidence_type: 'test_report', name: 'Standing loss test report' },
      { evidence_type: 'test_report', name: 'Abnormal operation test report' },
      { evidence_type: 'test_report', name: 'Impact / mechanical strength test report' },
      { evidence_type: 'test_report', name: 'Cord anchorage pull test report' },
      { evidence_type: 'test_report', name: 'Test finger accessibility test report' },
      { evidence_type: 'material_certificate', name: 'Inner container material certificate' },
      { evidence_type: 'material_certificate', name: 'Thermal insulation chloride-free certificate' },
      { evidence_type: 'document', name: 'Creepage and clearance design record' },
      ...COMMON_EVIDENCE,
    ],
  },
  'pressure-cooker': {
    attributes: [
      { key: 'body_material', label: 'Body material', type: 'select', options: ['Aluminium', 'Stainless steel', 'Hard anodised aluminium'] },
      { key: 'body_thickness_mm', label: 'Body wall thickness', type: 'number', unit: 'mm' },
      { key: 'base_thickness_mm', label: 'Base thickness', type: 'number', unit: 'mm' },
      { key: 'operating_pressure_kpa', label: 'Declared operating pressure', type: 'number', unit: 'kPa' },
      { key: 'primary_regulator_type', label: 'Primary regulating device', type: 'select', options: ['Vent weight', 'Spring loaded valve'] },
      { key: 'secondary_safety_device_fitted', label: 'Secondary safety device fitted', type: 'boolean' },
      { key: 'lid_interlock_fitted', label: 'Lid interlock fitted', type: 'boolean' },
    ],
    evidence: [
      { evidence_type: 'test_report', name: 'Hydrostatic burst test report' },
      { evidence_type: 'test_report', name: 'Safety device functional test report' },
      { evidence_type: 'test_report', name: 'Boiling and handle temperature test report' },
      { evidence_type: 'test_report', name: 'Gasket endurance (500 cycle) test report' },
      { evidence_type: 'test_report', name: 'Handle static load test report' },
      { evidence_type: 'test_report', name: 'Food contact migration test report' },
      { evidence_type: 'material_certificate', name: 'Body material batch certificate' },
      ...COMMON_EVIDENCE,
    ],
  },
  toy: {
    attributes: [
      { key: 'age_group_min_months', label: 'Minimum age', type: 'number', unit: 'months' },
      { key: 'has_small_parts', label: 'Contains or can release small parts', type: 'boolean' },
      { key: 'has_cords', label: 'Has cords, strings or elastics', type: 'boolean' },
      { key: 'cord_length_mm', label: 'Longest cord length', type: 'number', unit: 'mm' },
      { key: 'toy_materials', label: 'Materials used', type: 'text' },
    ],
    evidence: [
      { evidence_type: 'test_report', name: 'Small parts cylinder test report' },
      { evidence_type: 'test_report', name: 'Sharp edge and sharp point test report' },
      { evidence_type: 'test_report', name: 'Drop test report' },
      { evidence_type: 'test_report', name: 'Torque test report' },
      { evidence_type: 'test_report', name: 'Tension and pull test report' },
      { evidence_type: 'test_report', name: 'Compression test report' },
      { evidence_type: 'test_report', name: 'Element migration (heavy metals) test report' },
      { evidence_type: 'marking_artwork', name: 'Choking hazard warning artwork' },
      { evidence_type: 'document', name: 'Supplier declaration of pigments and plasticisers' },
      { evidence_type: 'document', name: 'Material and colour change control record' },
      ...COMMON_EVIDENCE,
    ],
  },
  helmet: {
    attributes: [
      { key: 'helmet_type', label: 'Helmet type', type: 'select', options: ['Full face', 'Open face', 'Half coverage'] },
      { key: 'shell_material', label: 'Shell material', type: 'text' },
      { key: 'liner_density_kg_m3', label: 'Protective padding density', type: 'number', unit: 'kg/m³' },
      { key: 'mass_kg', label: 'Complete helmet mass', type: 'number', unit: 'kg' },
      { key: 'peripheral_vision_deg', label: 'Peripheral field of vision', type: 'number', unit: '°' },
      { key: 'visor_transmittance_percent', label: 'Visor luminous transmittance', type: 'number', unit: '%' },
    ],
    evidence: [
      { evidence_type: 'test_report', name: 'Impact absorption test report' },
      { evidence_type: 'test_report', name: 'Penetration test report' },
      { evidence_type: 'test_report', name: 'Retention system test report' },
      { evidence_type: 'test_report', name: 'Roll-off test report' },
      { evidence_type: 'test_report', name: 'Field of vision test report' },
      { evidence_type: 'test_report', name: 'Conditioning record (four states)' },
      { evidence_type: 'test_report', name: 'Type test report covering all four conditioning states' },
      { evidence_type: 'test_report', name: 'Visor luminous transmittance test report' },
      { evidence_type: 'material_certificate', name: 'Shell material certificate' },
      { evidence_type: 'material_certificate', name: 'EPS liner batch certificate' },
      ...COMMON_EVIDENCE,
    ],
  },
  'electrical-appliance': {
    attributes: [
      { key: 'voltage_v', label: 'Rated voltage', type: 'number', unit: 'V' },
      { key: 'power_w', label: 'Rated power input', type: 'number', unit: 'W' },
      { key: 'protection_class', label: 'Protection class', type: 'select', options: ['I', 'II'] },
      { key: 'earth_continuity_ohm', label: 'Measured earth continuity', type: 'number', unit: 'Ω' },
      { key: 'supply_cord_csa_mm2', label: 'Supply cord cross-section', type: 'number', unit: 'mm²' },
    ],
    evidence: [
      { evidence_type: 'test_report', name: 'Temperature rise test report' },
      { evidence_type: 'test_report', name: 'Electric strength test report' },
      { evidence_type: 'test_report', name: 'Earth continuity test report' },
      { evidence_type: 'test_report', name: 'Abnormal operation test report' },
      { evidence_type: 'test_report', name: 'Impact / mechanical strength test report' },
      { evidence_type: 'test_report', name: 'Cord anchorage pull test report' },
      ...COMMON_EVIDENCE,
    ],
  },
}

export const FALLBACK_FORM: CategoryForm = {
  attributes: [],
  evidence: COMMON_EVIDENCE,
}

export function formFor(category: string): CategoryForm {
  return GAP_FORMS[category] ?? FALLBACK_FORM
}
