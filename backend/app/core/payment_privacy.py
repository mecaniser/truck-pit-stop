"""Secret-bearing validation/exception data never crosses the EFS boundary."""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse

PRIVATE={'Cache-Control':'no-store, private','Pragma':'no-cache','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}
class SensitivePaymentRoute(APIRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def safe(request):
            efs='/efs' in request.url.path
            try:return await handler(request)
            except RequestValidationError:
                raise HTTPException(422,detail={'code':'payment_fields_invalid','message':'Check the payment fields and try again.'},headers=PRIVATE) from None
            except HTTPException as exc:
                if efs:exc.headers={**(exc.headers or {}),**PRIVATE}
                raise
            except Exception as exc:
                from app.services.invoice_settlement_service import SettlementDomainError
                if not efs:raise
                if isinstance(exc,SettlementDomainError):
                    return JSONResponse(status_code=exc.status_code,content={'error':{'code':exc.code,'message':str(exc),'retryable':exc.retryable,'current_version':exc.current_version}},headers=PRIVATE)
                from app.core.logging import get_logger
                get_logger(__name__).error('efs_operation_failed',error_type=type(exc).__name__)
                return JSONResponse(status_code=500,content={'error':{'code':'efs_operation_failed','message':'EFS could not complete this request. Refresh its status before trying again.'}},headers=PRIVATE)
        return safe
