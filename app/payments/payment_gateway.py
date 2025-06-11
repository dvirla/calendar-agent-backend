import os
from paddle_billing import Environment, Client, Options
from paddle_billing.Resources.Transactions.Operations import CreateTransaction, ListTransactions
from paddle_billing.Resources.Customers.Operations import CreateCustomer, ListCustomers
from paddle_billing.Resources.Subscriptions.Operations import ListSubscriptions
from paddle_billing.Resources.Shared.Operations.List.Pager import Pager
from paddle_billing.Entities.Subscription import SubscriptionStatus
from paddle_billing.Resources.Products.Operations import ListProducts
from paddle_billing.Resources.Prices.Operations import ListPrices
from paddle_billing.Resources.Transactions.Operations.Create.TransactionCreateItem import TransactionCreateItem
from paddle_billing.Resources.Transactions.Operations.Create.TransactionCreateItemWithPrice import TransactionCreateItemWithPrice
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
import logging
import asyncio
import json
from dotenv import load_dotenv
from payments_data_classes import (
    PaymentRequest,
    PaymentResponse,
    RefundRequest,
    RefundResponse,
    CustomerRequest,
    CustomerResponse,
    SubscriptionResponse,
)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


class PaymentGateway:
    def __init__(self):
        api_key = os.getenv("PADDLE_API_KEY")
        environment = Environment.SANDBOX if os.getenv("PADDLE_ENVIRONMENT") == "sandbox" else Environment.PRODUCTION
        
        if not api_key:
            logger.warning("PADDLE_API_KEY not found in environment variables")
            
        options = Options(environment=environment)
        self.paddle = Client(api_key=api_key, options=options)
        self.environment = environment

    async def create_payment_intent(self, payment_request: PaymentRequest, price_id: str = None) -> PaymentResponse:
        try:
            # Option 1: Use existing catalog price (recommended)
            if price_id:
                item = TransactionCreateItem(
                    price_id=price_id,
                    quantity=1
                )
                transaction_request = CreateTransaction(
                    items=[item],
                    custom_data=payment_request.metadata or {}
                )
            else:
                # Option 2: Create ad-hoc price (requires proper structure)
                # Create ad-hoc price structure
                price_data = {
                    "description": payment_request.description or "Payment",
                    "unit_price": {
                        "amount": str(payment_request.amount),
                        "currency_code": payment_request.currency.upper()
                    }
                }
                item = TransactionCreateItemWithPrice(
                    price=price_data,
                    quantity=1
                )
                transaction_request = CreateTransaction(
                    items=[item],
                    custom_data=payment_request.metadata or {}
                )
            transaction = self.paddle.transactions.create(transaction_request)
            return PaymentResponse(
                payment_intent_id=transaction.id,
                client_secret=transaction.checkout.url if transaction.checkout else "",
                status=transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status),
                amount=payment_request.amount,
                currency=payment_request.currency
            )
        except Exception as e:
            logger.error(f"Paddle error creating transaction: {e}")
            raise Exception(f"Payment creation failed: {str(e)}")

    async def list_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List products from your Paddle catalog"""
        try:
            pager = Pager(per_page=limit)
            list_params = ListProducts(pager=pager)
            products = self.paddle.products.list(list_params)
            return [
                {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "status": product.status.value if hasattr(product.status, 'value') else str(product.status),
                    "created": product.created_at
                }
                for product in products
            ]
        except Exception as e:
            logger.error(f"Paddle error listing products: {e}")
            raise Exception(f"Product listing failed: {str(e)}")

    async def list_prices(self, product_id: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """List prices from your Paddle catalog"""
        try:
            pager = Pager(per_page=limit)
            if product_id:
                list_params = ListPrices(pager=pager, product_ids=[product_id])
            else:
                list_params = ListPrices(pager=pager)
            prices = self.paddle.prices.list(list_params)
            return [
                {
                    "id": price.id,
                    "product_id": price.product_id,
                    "description": price.description,
                    "name": price.name,
                    "unit_price_amount": price.unit_price.amount,
                    "unit_price_currency": price.unit_price.currency_code.value if hasattr(price.unit_price.currency_code, 'value') else str(price.unit_price.currency_code),
                    "billing_cycle": f"{price.billing_cycle.frequency} {price.billing_cycle.interval}" if price.billing_cycle else "one-time",
                    "status": price.status.value if hasattr(price.status, 'value') else str(price.status),
                    "created": price.created_at
                }
                for price in prices
            ]
        except Exception as e:
            logger.error(f"Paddle error listing prices: {e}")
            raise Exception(f"Price listing failed: {str(e)}")

    async def refund_payment(self, refund_request: RefundRequest) -> RefundResponse:
        try:
            #TODO: Check function
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
                amount=refund_request.amount or (int(float(transaction.details.totals.grand_total)) if transaction.details and transaction.details.totals and transaction.details.totals.grand_total else 0),
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
                created=customer.created_at
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
                created=customer.created_at
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
                    "amount": int(float(transaction.details.totals.grand_total)) if transaction.details and transaction.details.totals and transaction.details.totals.grand_total else 0,
                    "currency": transaction.currency_code if hasattr(transaction, 'currency_code') else "USD",
                    "status": transaction.status.value if hasattr(transaction.status, 'value') else str(transaction.status),
                    "created": transaction.created_at,
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
            list_params = ListSubscriptions(customer_ids=[customer_id], statuses=[SubscriptionStatus.Active])
            subscriptions = self.paddle.subscriptions.list(list_params)
            subscription_list = list(subscriptions) if subscriptions else []
            if not subscription_list:
                return None
            
            subscription = subscription_list[0]  # Get the first active subscription
            return SubscriptionResponse(
                subscription_id=subscription.id,
                customer_id=subscription.customer_id,
                status=subscription.status.value if hasattr(subscription.status, 'value') else str(subscription.status),
                current_period_start=subscription.current_billing_period.starts_at,
                current_period_end=subscription.current_billing_period.ends_at,
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
            from datetime import timezone
            now = datetime.now(timezone.utc)
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
        costumer_subscription = await payment_gateway.get_customer_subscription(customer.customer_id)
        logger.info(f"costumer_subscription {customer.name} costumer_subscription: {costumer_subscription.subscription_id}")
        payments = await payment_gateway.list_payments(customer.customer_id)
        if payments:
            logger.info(f"payments {payments} ")
        
async def run_catalog_demo():
    """Demo function showing how to use your Paddle catalog"""
    payment_gateway = PaymentGateway()
    
    try:
        # 1. List your products
        logger.info("=== Listing Products ===")
        products = await payment_gateway.list_products()
        for product in products:
            logger.info(f"Product: {product['id']} - {product['name']} - {product['description']}")
        
        # 2. List your prices
        logger.info("=== Listing Prices ===")
        prices = await payment_gateway.list_prices()
        for price in prices:
            logger.info(f"Price: {price['id']} - {price['description']} - {price['unit_price_amount']} {price['unit_price_currency']}")
        
        # 3. Create a transaction using a catalog price (if you have any)
        if prices:
            price_id = prices[0]['id']  # Use the first price
            logger.info(f"=== Creating transaction with price_id: {price_id} ===")
            
            payment_request = PaymentRequest(
                amount=100,  # This will be ignored when using catalog price
                currency="USD",
                description="Test Payment with Catalog Price",
                metadata={"test_key": "test_value"}
            )
            
            response = await payment_gateway.create_payment_intent(
                payment_request, 
                price_id=price_id  # Use catalog price
            )
            logger.info(f"Transaction created: {response.payment_intent_id}")
        else:
            logger.info("No prices found in catalog. Create products and prices in Paddle dashboard first.")
            
    except Exception as e:
        logger.error(f"Demo failed: {e}")

async def run_create_customer_test():
    payment_gateway = PaymentGateway()
    import uuid
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    customer_request = CustomerRequest(
        email=unique_email,
        name="Test User",
        phone="+1234567890",
    )
    response = await payment_gateway.create_customer(customer_request)
    logger.info(f"create_customer response {response.customer_id} ")

        

if __name__ == "__main__":
    # asyncio.run(main())
    # asyncio.run(run_create_customer_test())
    asyncio.run(run_catalog_demo())