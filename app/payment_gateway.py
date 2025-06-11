import os
from paddle_billing import Environment, Client, Options
from paddle_billing.Resources.Transactions.Operations import CreateTransaction, ListTransactions
from paddle_billing.Resources.Customers.Operations import CreateCustomer, ListCustomers
from paddle_billing.Resources.Subscriptions.Operations import ListSubscriptions
from paddle_billing.Resources.Shared.Operations.List.Pager import Pager
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
import logging
import asyncio
import json
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

class PaymentRequest(BaseModel):
    amount: int  # Amount in cents
    currency: str = "usd"
    description: Optional[str] = None
    customer_email: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

class PaymentResponse(BaseModel):
    payment_intent_id: str
    client_secret: str
    status: str
    amount: int
    currency: str

class RefundRequest(BaseModel):
    payment_intent_id: str
    amount: Optional[int] = None  # If None, refunds full amount
    reason: Optional[str] = None

class RefundResponse(BaseModel):
    refund_id: str
    status: str
    amount: int
    currency: str

class CustomerRequest(BaseModel):
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

class CustomerResponse(BaseModel):
    customer_id: str
    email: str
    name: Optional[str] = None
    created: datetime

class SubscriptionResponse(BaseModel):
    subscription_id: str
    customer_id: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    plan_id: str
    plan_name: Optional[str] = None

class PaymentGateway:
    def __init__(self):
        api_key = os.getenv("PADDLE_API_KEY")
        environment = Environment.SANDBOX if os.getenv("PADDLE_ENVIRONMENT") == "sandbox" else Environment.PRODUCTION
        
        if not api_key:
            logger.warning("PADDLE_API_KEY not found in environment variables")
            
        options = Options(environment=environment)
        self.paddle = Client(api_key=api_key, options=options)
        self.environment = environment

    async def create_payment_intent(self, payment_request: PaymentRequest) -> PaymentResponse:
        try:
            # Create transaction with Paddle
            transaction_request = CreateTransaction(
                items=[
                    {
                        "price": {
                            "description": payment_request.description or "Payment",
                            "unit_price": {
                                "amount": str(payment_request.amount),
                                "currency_code": payment_request.currency.upper()
                            }
                        },
                        "quantity": 1
                    }
                ],
                customer_email=payment_request.customer_email,
                custom_data=payment_request.metadata or {}
            )
            
            transaction = self.paddle.transactions.create(transaction_request)
            
            return PaymentResponse(
                payment_intent_id=transaction.id,
                client_secret=transaction.checkout.url if transaction.checkout else "",
                status=transaction.status,
                amount=payment_request.amount,
                currency=payment_request.currency
            )
        except Exception as e:
            logger.error(f"Paddle error creating transaction: {e}")
            raise Exception(f"Payment creation failed: {str(e)}")

    async def confirm_payment(self, payment_intent_id: str) -> Dict[str, Any]:
        try:
            transaction = self.paddle.transactions.get(payment_intent_id)
            return {
                "id": transaction.id,
                "status": transaction.status,
                "amount": int(transaction.details.totals.grand_total.amount) if transaction.details else 0,
                "currency": transaction.currency_code if hasattr(transaction, 'currency_code') else "USD",
                "charges": [{
                    "id": transaction.id,
                    "amount": int(transaction.details.totals.grand_total.amount) if transaction.details else 0,
                    "status": transaction.status,
                    "receipt_url": transaction.receipt_data.url if transaction.receipt_data else None
                }]
            }
        except Exception as e:
            logger.error(f"Paddle error confirming payment: {e}")
            raise Exception(f"Payment confirmation failed: {str(e)}")

    async def refund_payment(self, refund_request: RefundRequest) -> RefundResponse:
        try:
            # Get the original transaction first
            transaction = self.paddle.transactions.get(refund_request.payment_intent_id)
            
            # Create adjustment for refund
            adjustment_items = []
            if refund_request.amount:
                adjustment_items.append({
                    "type": "partial",
                    "amount": str(refund_request.amount),
                    "transaction_id": refund_request.payment_intent_id
                })
            else:
                adjustment_items.append({
                    "type": "full",
                    "transaction_id": refund_request.payment_intent_id
                })
            
            # Note: Paddle uses adjustments for refunds
            adjustment = self.paddle.adjustments.create({
                "action": "refund",
                "items": adjustment_items,
                "reason": refund_request.reason or "Refund requested"
            })
            
            return RefundResponse(
                refund_id=adjustment.id,
                status="processed",
                amount=refund_request.amount or (int(transaction.details.totals.grand_total.amount) if transaction.details else 0),
                currency=transaction.currency_code if hasattr(transaction, 'currency_code') else "USD"
            )
        except Exception as e:
            logger.error(f"Paddle error processing refund: {e}")
            raise Exception(f"Refund failed: {str(e)}")

    async def create_customer(self, customer_request: CustomerRequest) -> CustomerResponse:
        try:
            customer_data = CreateCustomer(
                email=customer_request.email,
                name=customer_request.name
            )
            
            customer = self.paddle.customers.create(customer_data)
            
            return CustomerResponse(
                customer_id=customer.id,
                email=customer.email,
                name=customer.name,
                created=datetime.fromisoformat(customer.created_at.replace('Z', '+00:00'))
            )
        except Exception as e:
            logger.error(f"Paddle error creating customer: {e}")
            raise Exception(f"Customer creation failed: {str(e)}")

    async def get_customer(self, customer_id: str) -> CustomerResponse:
        try:
            customer = self.paddle.customers.get(customer_id)
            
            return CustomerResponse(
                customer_id=customer.id,
                email=customer.email,
                name=customer.name,
                created=datetime.fromisoformat(customer.created_at.replace('Z', '+00:00'))
            )
        except Exception as e:
            logger.error(f"Paddle error retrieving customer: {e}")
            raise Exception(f"Customer retrieval failed: {str(e)}")

    async def list_payments(self, customer_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            pager = Pager(per_page=limit)
            list_params = ListTransactions(pager=pager)
            if customer_id:
                list_params = ListTransactions(pager=pager, customer_ids=[customer_id])
            
            transactions = self.paddle.transactions.list(list_params)
            
            return [
                {
                    "id": transaction.id,
                    "amount": int(transaction.details.totals.grand_total.amount) if transaction.details else 0,
                    "currency": transaction.currency_code if hasattr(transaction, 'currency_code') else "USD",
                    "status": transaction.status,
                    "created": datetime.fromisoformat(transaction.created_at.replace('Z', '+00:00')),
                    "description": transaction.origin if hasattr(transaction, 'origin') else None,
                    "customer": transaction.customer_id
                }
                for transaction in transactions
            ]
        except Exception as e:
            logger.error(f"Paddle error listing payments: {e}")
            raise Exception(f"Payment listing failed: {str(e)}")

    def get_publishable_key(self) -> str:
        # Paddle doesn't use publishable keys in the same way as Stripe
        return os.getenv("PADDLE_CLIENT_TOKEN", "")

    async def handle_webhook(self, payload: str, sig_header: str) -> Dict[str, Any]:
        webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET")
        
        if not webhook_secret:
            raise Exception("Webhook secret not configured")

        try:
            # Paddle webhook verification
            from paddle_billing.Notifications import Verifier
            verifier = Verifier()
            
            if not verifier.verify(payload, sig_header, webhook_secret):
                raise Exception("Invalid signature")
            
            event = json.loads(payload)
        except ValueError as e:
            logger.error(f"Invalid payload: {e}")
            raise Exception("Invalid payload")
        except Exception as e:
            logger.error(f"Webhook verification failed: {e}")
            raise Exception("Invalid signature")

        event_type = event.get('event_type', '')
        if event_type == 'transaction.completed':
            transaction = event['data']
            logger.info(f"Payment succeeded: {transaction['id']}")
        elif event_type == 'transaction.payment_failed':
            transaction = event['data']
            logger.warning(f"Payment failed: {transaction['id']}")
        
        return {"status": "success", "event_type": event_type}

    async def get_customer_subscription(self, customer_id: str) -> Optional[SubscriptionResponse]:
        try:
            list_params = ListSubscriptions(customer_ids=[customer_id], statuses=["active"])
            subscriptions = self.paddle.subscriptions.list(list_params)
            
            if not subscriptions:
                return None
            
            subscription = subscriptions[0]  # Get the first active subscription
            
            return SubscriptionResponse(
                subscription_id=subscription.id,
                customer_id=subscription.customer_id,
                status=subscription.status,
                current_period_start=datetime.fromisoformat(subscription.current_billing_period.starts_at.replace('Z', '+00:00')),
                current_period_end=datetime.fromisoformat(subscription.current_billing_period.ends_at.replace('Z', '+00:00')),
                plan_id=subscription.items[0].price.id if subscription.items else "",
                plan_name=subscription.items[0].price.name if subscription.items else None
            )
        except Exception as e:
            logger.error(f"Paddle error retrieving subscription: {e}")
            raise Exception(f"Subscription retrieval failed: {str(e)}")

    async def is_subscription_valid(self, customer_id: str) -> bool:
        try:
            subscription = await self.get_customer_subscription(customer_id)
            
            if not subscription:
                return False
            
            # Check if subscription is active and not expired
            now = datetime.now()
            return (
                subscription.status == 'active' and 
                subscription.current_period_end > now
            )
        except Exception as e:
            logger.error(f"Error checking subscription validity: {e}")
            return False

    async def get_all_customers_and_log(self, limit: int = 100) -> List[CustomerResponse]:
        try:
            logger.info(f"Retrieving all customers (limit: {limit})")
            pager = Pager(per_page=limit)
            list_params = ListCustomers(pager=pager)
            customers = self.paddle.customers.list(list_params)
            customer_list = []
            for customer in customers:
                customer_response = CustomerResponse(
                    customer_id=customer.id,
                    email=customer.email or "No email",
                    name=customer.name,
                    created=customer.created_at
                )
                customer_list.append(customer_response)
                logger.info(f"Customer: {customer.id} | Email: {customer.email or 'No email'} | Name: {customer.name or 'No name'} | Created: {customer_response.created}")
            logger.info(f"Total customers retrieved: {len(customer_list)}")
            return customer_list
            
        except Exception as e:
            logger.error(f"Paddle error retrieving customers: {e}")
            raise Exception(f"Customer retrieval failed: {str(e)}")
        
        
async def main():
    payment_gateway = PaymentGateway()
    customer_list = await payment_gateway.get_all_customers_and_log()
    
    # Process each customer's subscription validity
    for customer in customer_list:
        is_valid = await payment_gateway.is_subscription_valid(customer.customer_id)
        logger.info(f"Customer {customer.customer_id} subscription valid: {is_valid}")

if __name__ == "__main__":
    asyncio.run(main())