import { createContext, useContext } from 'react'

// Standalone panels are visible; an order workspace supplies its initial reveal state.
export const OrderSurfaceContext = createContext(true)
export const useOrderSurfaceVisible = () => useContext(OrderSurfaceContext)
