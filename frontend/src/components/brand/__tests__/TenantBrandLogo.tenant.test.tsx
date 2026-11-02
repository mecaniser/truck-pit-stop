import {render,screen,fireEvent} from '@testing-library/react'
import {it,expect} from 'vitest'
import TenantBrandLogo from '../TenantBrandLogo'
it('uses the tenant name when the tenant has no logo',()=>{
 render(<TenantBrandLogo tenantOnly tenantName="Truck Pit Stop" />)
 expect(screen.getByRole('img',{name:'Truck Pit Stop'})).toHaveTextContent('Truck Pit Stop')
 expect(screen.queryByRole('img',{name:/Diesel Bridge/})).not.toBeInTheDocument()
})
it('keeps tenant branding if its logo fails to load',()=>{
 render(<TenantBrandLogo tenantOnly tenantName="Another Shop" tenantLogoUrl="https://example.test/logo.png" />)
 fireEvent.error(screen.getByRole('img'))
 expect(screen.getByRole('img',{name:'Another Shop'})).toHaveTextContent('Another Shop')
})
