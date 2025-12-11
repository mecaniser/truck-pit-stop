import { useQuery } from '@tanstack/react-query'
import api from '../../lib/api'
import { Vehicle } from '../../types'

export default function VehiclesPage() {
  const { data: vehicles, isLoading } = useQuery<Vehicle[]>({
    queryKey: ['vehicles'],
    queryFn: async () => {
      const response = await api.get('/vehicles')
      return response.data
    },
  })

  if (isLoading) {
    return <div>Loading...</div>
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Vehicles</h1>
      <div className="bg-white shadow overflow-hidden sm:rounded-md">
        <ul className="divide-y divide-gray-200">
          {vehicles?.map((vehicle) => (
            <li key={vehicle.id}>
              <div className="px-4 py-4 sm:px-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-indigo-600 truncate">
                    {vehicle.year} {vehicle.make} {vehicle.model}
                  </p>
                </div>
                <div className="mt-2 sm:flex sm:justify-between">
                  <div className="sm:flex">
                    {vehicle.vin && (
                      <p className="flex items-center text-sm text-gray-500">
                        VIN: {vehicle.vin}
                      </p>
                    )}
                    {vehicle.license_plate && (
                      <p className="mt-2 flex items-center text-sm text-gray-500 sm:mt-0 sm:ml-6">
                        Plate: {vehicle.license_plate}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

