import logging
from typing import Optional

import ormar
import stripe
from sqlalchemy import select

from association.domain.entities.stripe import (
    StripeCheckoutSession,
    StripeCustomer,
    StripeSubscription,
    StripeSubscriptionStatus,
)
from association.domain.exceptions import (
    MultipleCustomerReturned,
    MultipleCustomerSubscriptionsReturned,
    StripeSubscriptionNotFound,
)
from association.settings import (
    DOMAIN_URL,
    STRIPE_SECRET_API_KEY,
    STRIPE_SUBSCRIPTION_PRICE_ID,
)
from association_membership.domain.entities import (
    Subscription,
    SubscriptionInvoice,
    SubscriptionStatus,
)
from customers.domain.entities import Customer

logger = logging.getLogger(__name__)


class AssociationMembershipRepository:
    async def get_by_stripe_id(
        self, stripe_subscription_id: str
    ) -> Optional[Subscription]:
        return await Subscription.objects.get_or_none(
            stripe_subscription_id=stripe_subscription_id
        )

    async def get_or_create_subscription(
        self,
        *,
        customer: Customer,
        stripe_subscription_id: str,
    ) -> Subscription:
        try:
            subscription = await Subscription.objects.get(
                stripe_subscription_id=stripe_subscription_id
            )

            if subscription.customer.id != customer.id:
                raise ValueError(
                    "Subscription X found but assigned to another customer"
                )
        except ormar.NoMatch:
            subscription = await Subscription.objects.create(
                stripe_subscription_id=stripe_subscription_id,
                customer=customer,
                status=SubscriptionStatus.PENDING,
            )

        return subscription

    async def save_subscription(self, subscription: Subscription) -> Subscription:
        """ TODO Test Create or Update """
        await subscription.update()

        for invoice in subscription._add_invoice:
            # invoices to add
            invoice.subscription = subscription
            await invoice.save()

            await subscription.subscriptioninvoices.add(invoice)

        return subscription

    # =====================================

    # READ
    async def get_subscription_by_stripe_subscription_id(
        self, stripe_subscription_id: str
    ) -> Optional[Subscription]:
        query = select(Subscription).where(
            Subscription.stripe_subscription_id == stripe_subscription_id
        )
        subscription = (await self.session.execute(query)).scalar_one_or_none()
        return subscription

    async def get_subscription_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[Subscription]:
        query = select(Subscription).where(
            Subscription.stripe_customer_id == stripe_customer_id
        )
        subscription = (await self.session.execute(query)).scalar_one_or_none()
        return subscription

    async def get_subscription_by_user_id(self, user_id: int) -> Optional[Subscription]:
        query = select(Subscription).where(Subscription.user_id == user_id)
        subscription = (await self.session.execute(query)).scalar_one_or_none()
        return subscription

    # WRITE

    async def delete_subscription(self, subscription: Subscription) -> None:
        self.session.delete(subscription)
        await self.session.flush()
        return None

    async def save_payment(
        self, subscription_payment: SubscriptionInvoice
    ) -> SubscriptionInvoice:
        """ TODO Test ME """
        self.session.add(subscription_payment)
        await self.session.flush()
        return subscription_payment

    async def get_payment_by_stripe_invoice_id(
        self, stripe_invoice_id: str
    ) -> SubscriptionInvoice:
        """ TODO Test ME """
        query = select(SubscriptionInvoice).where(
            SubscriptionInvoice.stripe_invoice_id == stripe_invoice_id
        )
        payment = (await self.session.execute(query)).scalar_one_or_none()
        return payment

    # ============== #
    #    Stripe
    # ============== #
    async def create_checkout_session(self, customer_id: str) -> StripeCheckoutSession:
        """ TODO Test ME """
        # See https://stripe.com/docs/api/checkout/sessions/create
        # for additional parameters to pass.
        # {CHECKOUT_SESSION_ID} is a string literal; do not change it!
        # the actual Session ID is returned in the query parameter when your customer
        # is redirected to the success page.
        # checkout_session_stripe_key = "{CHECKOUT_SESSION_ID}"
        checkout_session = stripe.checkout.Session.create(
            success_url="https://example.org",
            cancel_url="https://example.org",
            payment_method_types=["card"],
            mode="subscription",
            customer=customer_id,
            line_items=[
                {
                    "price": STRIPE_SUBSCRIPTION_PRICE_ID,
                    "quantity": 1,
                }
            ],
            api_key=STRIPE_SECRET_API_KEY,
        )
        logger.info(f"checkout_session: {checkout_session}")
        return StripeCheckoutSession(
            id=checkout_session["id"],
            customer_id=checkout_session["customer"] or "",
            subscription_id=checkout_session["subscription"] or "",
        )

    async def retrieve_customer_portal_session_url(self, customer_id: str) -> str:
        """ TODO Test ME """
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=DOMAIN_URL,
            api_key=STRIPE_SECRET_API_KEY,
        )
        return session.url

    async def _retrieve_customer_by_email(self, email: str) -> Optional[StripeCustomer]:
        """ TODO Test ME """
        customers = stripe.Customer.list(email=email, api_key=STRIPE_SECRET_API_KEY)

        if len(customers.data) > 1:
            raise MultipleCustomerReturned()

        customer = customers.data[0] if customers.data else None
        return StripeCustomer(id=customer.id, email=email) if customer else None

    async def _create_customer_by_email(self, email: str) -> StripeCustomer:
        """ TODO Test ME """
        customer = stripe.Customer.create(email=email, api_key=STRIPE_SECRET_API_KEY)
        return StripeCustomer(id=customer.id, email=email)

    async def get_or_create_customer_by_email(self, email: str) -> StripeCustomer:
        """ TODO Test ME """
        customer: StripeCustomer = await self._retrieve_customer_by_email(email)

        if customer:
            return customer

        customer: StripeCustomer = await self._create_customer_by_email(email)
        return customer

    async def _retrieve_stripe_subscription_by_stripe_subscription_id(
        self, stripe_subscription_id: str
    ) -> Optional[StripeSubscription]:
        """ TODO Test ME """
        stripe_subscription = stripe.Subscription.retrieve(
            stripe_subscription_id, api_key=STRIPE_SECRET_API_KEY
        )
        logger.info(f"stripe_subscription: {stripe_subscription}")
        return StripeSubscription(
            id=stripe_subscription["id"],
            status=stripe_subscription["status"],
            customer_id=stripe_subscription["customer"],
            canceled_at=stripe_subscription["canceled_at"],
        )

    async def _retrieve_stripe_subscription_by_stripe_customer_id(
        self, stripe_customer_id: str, **kwargs
    ) -> Optional[StripeSubscription]:
        """ TODO Test ME """
        stripe_subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            api_key=STRIPE_SECRET_API_KEY,
            status=StripeSubscriptionStatus.ACTIVE,
            **kwargs,
        )
        if len(stripe_subscriptions.data) == 1:
            stripe_subscription = stripe_subscriptions.data[0]
            return StripeSubscription(
                id=stripe_subscription["id"],
                status=stripe_subscription["status"],
                customer_id=stripe_subscription["customer"],
                canceled_at=stripe_subscription["canceled_at"],
            )
        elif len(stripe_subscriptions.data) > 1:
            subs = list(
                filter(
                    lambda x: x.status
                    not in [
                        StripeSubscriptionStatus.CANCELED,
                        StripeSubscriptionStatus.UNPAID,
                        StripeSubscriptionStatus.INCOMPLETE_EXPIRED,
                    ],
                    stripe_subscriptions.data,
                )
            )
            if len(subs) > 1:
                # TODO : quando una subscription viene cancellata, bisogna far si che ne possa creare una nuova su Stripe in un qualsiasi momento
                # Attualmente questa eccezione dovrebbe bloccare l'utente
                # Le API permettono di fare la seguente query: ?status=active&status=past_due -> restituisce status__in=[active,past_due], ora bisogna capire se il metodo list lo supporti
                raise MultipleCustomerSubscriptionsReturned()
            else:
                return subs and subs[0] or None
        return None

    async def sync_with_external_service(
        self, subscription: Subscription, **kwargs
    ) -> Optional[Subscription]:
        """ TODO Test ME """
        if subscription.stripe_subscription_id:
            stripe_subscription: StripeSubscription = (
                await self._retrieve_stripe_subscription_by_stripe_subscription_id(
                    subscription.stripe_subscription_id, **kwargs
                )
            )
        else:
            try:
                stripe_subscription: StripeSubscription = (
                    await self._retrieve_stripe_subscription_by_stripe_customer_id(
                        subscription.stripe_customer_id, **kwargs
                    )
                )
            except MultipleCustomerSubscriptionsReturned as ex:
                raise ex
        if not stripe_subscription:
            raise StripeSubscriptionNotFound()
        return subscription.sync_with_stripe_subscription(stripe_subscription)
