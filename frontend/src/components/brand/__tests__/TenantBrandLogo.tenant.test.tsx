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

it('can leave a separate tenant name visible when a compact header logo is missing or fails', () => {
 const {rerender}=render(<><TenantBrandLogo tenantOnly hideTextFallback tenantName="Another Shop" /><span>Another Shop</span></>)
 expect(screen.getAllByText('Another Shop')).toHaveLength(1)
 expect(screen.queryByRole('img')).not.toBeInTheDocument()
 rerender(<><TenantBrandLogo tenantOnly hideTextFallback tenantName="Another Shop" tenantLogoUrl="https://example.test/shop.png" /><span>Another Shop</span></>)
 expect(screen.getByRole('img',{name:'Another Shop logo'})).toHaveAttribute('src','https://example.test/shop.png')
 expect(screen.getAllByText('Another Shop')).toHaveLength(1)
 fireEvent.error(screen.getByRole('img'))
 expect(screen.getAllByText('Another Shop')).toHaveLength(1)
 expect(screen.queryByRole('img')).not.toBeInTheDocument()
})
