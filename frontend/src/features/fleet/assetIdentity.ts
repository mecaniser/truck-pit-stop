import type { BoardTruck, EquipmentType } from './types'
export type AssetFilter = 'all' | EquipmentType
export const assetTypeLabel = (kind?: EquipmentType) => ({ tractor: 'Tractor', trailer: 'Trailer', unknown: 'Unclassified', other: 'Other equipment' }[kind || 'unknown'])
export const filterAssets = (assets: BoardTruck[], kind: AssetFilter) => kind === 'all' ? assets : assets.filter(asset => (asset.equipment_type || 'unknown') === kind)
