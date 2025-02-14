from custom_admin.admin import validate_single_conference_selection
from import_export.resources import ModelResource
from datetime import timedelta
from typing import Dict, List, Optional
from countries.filters import CountryFilter
from django.urls import path
from django.template.response import TemplateResponse
from django.db.models import Count, Sum
from helpers.constants import GENDERS
from django import forms
from django.contrib import admin, messages
from django.db.models.query import QuerySet
from django.utils import timezone
from import_export.admin import ExportMixin
from import_export.fields import Field
from django.utils.crypto import get_random_string
from users.admin_mixins import ConferencePermissionMixin
from countries import countries
from grants.tasks import (
    send_grant_reply_approved_email,
    send_grant_reply_waiting_list_email,
    send_grant_reply_waiting_list_update_email,
    send_grant_reply_rejected_email,
    send_grant_voucher_email,
)
from pretix import create_voucher
from schedule.models import ScheduleItem
from submissions.models import Submission
from .models import Grant
from django.db.models import Exists, OuterRef

from django.contrib.admin import SimpleListFilter

EXPORT_GRANTS_FIELDS = (
    "name",
    "full_name",
    "gender",
    "occupation",
    "grant_type",
    "python_usage",
    "been_to_other_events",
    "interested_in_volunteering",
    "needs_funds_for_travel",
    "why",
    "notes",
    "travelling_from",
    "conference__code",
    "created",
)


class GrantResource(ModelResource):
    search_field = "user_id"
    age_group = Field()
    email = Field()
    has_sent_submission = Field()
    submission_title = Field()
    submission_tags = Field()
    submission_admin_link = Field()
    submission_pycon_link = Field()
    grant_admin_link = Field()
    USERS_SUBMISSIONS: Dict[int, List[Submission]] = {}

    def dehydrate_email(self, obj: Grant):
        if obj.user_id:
            return obj.user.email

        # old grants have email in the model.
        return obj.email

    def dehydrate_age_group(self, obj: Grant):
        if not obj.age_group:
            return ""

        return Grant.AgeGroup(obj.age_group).label

    def dehydrate_has_sent_submission(self, obj: Grant) -> str:
        return "TRUE" if obj.user_id in self.USERS_SUBMISSIONS else "FALSE"

    def _get_submissions(self, obj: Grant) -> Optional[List[Submission]]:
        if not obj.user_id:
            return

        return self.USERS_SUBMISSIONS.get(obj.user_id)

    def dehydrate_submission_title(self, obj: Grant):
        submissions = self._get_submissions(obj)
        if not submissions:
            return

        return "\n".join([s.title.localize("en") for s in submissions])

    def dehydrate_submission_tags(self, obj: Grant):
        submissions = self._get_submissions(obj)
        if not submissions:
            return

        return "\n".join(
            [
                ", ".join(
                    [
                        f"{r.tag.name}: {r.rank} / {r.total_submissions_per_tag}"
                        for r in s.rankings.all()
                    ]
                )
                for s in submissions
            ]
        )

    def dehydrate_submission_pycon_link(self, obj):
        submissions = self.USERS_SUBMISSIONS.get(obj.user_id)
        if not submissions:
            return
        return "\n".join(
            [f"https://pycon.it/submission/{s.hashid}" for s in submissions]
        )

    def dehydrate_submission_admin_link(self, obj):
        submissions = self.USERS_SUBMISSIONS.get(obj.user_id)
        if not submissions:
            return
        return "\n".join(
            [
                f"https://admin.pycon.it/admin/submissions/submission/{s.id}/change/"
                for s in submissions
            ]
        )

    def dehydrate_grant_admin_link(self, obj: Grant):
        return f"https://admin.pycon.it/admin/grants/grant/?q={'+'.join(obj.full_name.split(' '))}"  # noqa: E501

    def before_export(self, queryset: QuerySet, *args, **kwargs):
        super().before_export(queryset, *args, **kwargs)
        conference_id = queryset.values_list("conference_id").first()

        submissions = Submission.objects.prefetch_related(
            "rankings__tag", "rankings__submission"
        ).filter(
            speaker_id__in=queryset.values_list("user_id", flat=True),
            conference_id=conference_id,
        )

        self.USERS_SUBMISSIONS = {}
        for submission in submissions:
            self.USERS_SUBMISSIONS.setdefault(submission.speaker_id, [])
            self.USERS_SUBMISSIONS[submission.speaker_id].append(submission)

        return queryset

    class Meta:
        model = Grant
        fields = EXPORT_GRANTS_FIELDS
        export_order = EXPORT_GRANTS_FIELDS


def _check_amounts_are_not_empty(grant: Grant, request):
    if grant.total_amount is None:
        messages.error(
            request,
            f"Grant for {grant.name} is missing 'Total Amount'!",
        )
        return False

    if grant.has_approved_accommodation() and grant.accommodation_amount is None:
        messages.error(
            request,
            f"Grant for {grant.name} is missing 'Accommodation Amount'!",
        )
        return False

    if grant.has_approved_travel() and grant.travel_amount is None:
        messages.error(
            request,
            f"Grant for {grant.name} is missing 'Travel Amount'!",
        )
        return False

    return True


@admin.action(description="Send Approved/Waiting List/Rejected reply emails")
@validate_single_conference_selection
def send_reply_emails(modeladmin, request, queryset):
    queryset = queryset.filter(
        status__in=(
            Grant.Status.approved,
            Grant.Status.waiting_list,
            Grant.Status.waiting_list_maybe,
            Grant.Status.rejected,
        ),
    )

    if not queryset:
        messages.add_message(
            request, messages.WARNING, "No grants found in the selection"
        )
        return

    for grant in queryset:
        if grant.status in (Grant.Status.approved,):
            if grant.approved_type is None:
                messages.error(
                    request,
                    f"Grant for {grant.name} is missing 'Grant Approved Type'!",
                )
                return

            if not _check_amounts_are_not_empty(grant, request):
                return

            now = timezone.now()
            grant.applicant_reply_deadline = timezone.datetime(
                now.year, now.month, now.day, 23, 59, 59
            ) + timedelta(days=14)
            grant.save()
            send_grant_reply_approved_email.delay(grant_id=grant.id, is_reminder=False)

            messages.info(request, f"Sent Approved reply email to {grant.name}")

        if (
            grant.status == Grant.Status.waiting_list
            or grant.status == Grant.Status.waiting_list_maybe
        ):
            send_grant_reply_waiting_list_email.delay(grant_id=grant.id)
            messages.info(request, f"Sent Waiting List reply email to {grant.name}")

        if grant.status == Grant.Status.rejected:
            send_grant_reply_rejected_email.delay(grant_id=grant.id)
            messages.info(request, f"Sent Rejected reply email to {grant.name}")


@admin.action(description="Send reminder to waiting confirmation grants")
@validate_single_conference_selection
def send_grant_reminder_to_waiting_for_confirmation(modeladmin, request, queryset):
    queryset = queryset.filter(
        status__in=(Grant.Status.waiting_for_confirmation,),
    )

    for grant in queryset:
        if not grant.grant_type:
            messages.add_message(
                request,
                messages.ERROR,
                f"Grant for {grant.name} is missing 'Grant Approved Type'!",
            )
            return

        _check_amounts_are_not_empty(grant, request)

        send_grant_reply_approved_email.delay(grant_id=grant.id, is_reminder=True)

        messages.info(request, f"Grant reminder sent to {grant.name}")


@admin.action(description="Send Waiting List update email")
@validate_single_conference_selection
def send_reply_email_waiting_list_update(modeladmin, request, queryset):
    queryset = queryset.filter(
        status__in=(
            Grant.Status.waiting_list,
            Grant.Status.waiting_list_maybe,
        ),
    )

    for grant in queryset:
        send_grant_reply_waiting_list_update_email.delay(grant_id=grant.id)
        messages.info(request, f"Sent Waiting List update reply email to {grant.name}")


@admin.action(description="Send voucher via email")
@validate_single_conference_selection
def send_voucher_via_email(modeladmin, request, queryset):
    count = 0
    for grant in queryset.filter(pretix_voucher_id__isnull=False):
        send_grant_voucher_email.delay(grant_id=grant.id)
        count = count + 1

    messages.success(request, f"{count} Voucher emails scheduled!")


def _generate_voucher_code(prefix: str) -> str:
    charset = list("ABCDEFGHKLMNPQRSTUVWXYZ23456789")
    random_string = get_random_string(length=20, allowed_chars=charset)
    return f"{prefix}-{random_string}"


@admin.action(description="Create grant vouchers on Pretix")
@validate_single_conference_selection
def create_grant_vouchers_on_pretix(modeladmin, request, queryset):
    conference = queryset.first().conference

    if not conference.pretix_speaker_voucher_quota_id:
        messages.error(
            request,
            "Please configure the grant voucher quota ID in the conference settings",
        )
        return

    count = 0
    for grant in queryset.filter(pretix_voucher_id__isnull=True):
        if grant.status != Grant.Status.confirmed:
            messages.error(
                request,
                f"Grant for {grant.name} is not confirmed, "
                "we can't generate voucher for it.",
            )
            continue

        voucher_code = _generate_voucher_code("GRANT")
        pretix_voucher = create_voucher(
            conference=grant.conference,
            code=voucher_code,
            comment=f"Voucher for user_id={grant.user_id}",
            tag="grants",
            quota_id=grant.conference.pretix_speaker_voucher_quota_id,
            price_mode="set",
            value="0.00",
        )

        pretix_voucher_id = pretix_voucher["id"]
        grant.pretix_voucher_id = pretix_voucher_id
        grant.voucher_code = voucher_code
        grant.save()
        count += 1

    messages.success(request, f"{count} Vouchers created on Pretix!")


class GrantAdminForm(forms.ModelForm):
    class Meta:
        model = Grant
        fields = (
            "id",
            "name",
            "status",
            "approved_type",
            "ticket_amount",
            "travel_amount",
            "accommodation_amount",
            "total_amount",
            "full_name",
            "conference",
            "user",
            "age_group",
            "gender",
            "occupation",
            "grant_type",
            "python_usage",
            "been_to_other_events",
            "interested_in_volunteering",
            "needs_funds_for_travel",
            "why",
            "notes",
            "travelling_from",
            "country_type",
            "applicant_message",
            "plain_thread_id",
            "applicant_reply_sent_at",
            "applicant_reply_deadline",
        )


class IsProposedSpeakerFilter(SimpleListFilter):
    title = "Is Proposed Speaker"
    parameter_name = "is_proposed_speaker"

    def lookups(self, request, model_admin):
        return (
            (True, "Yes"),
            (False, "No"),
        )

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(is_proposed_speaker=self.value())
        return queryset


class IsConfirmedSpeakerFilter(SimpleListFilter):
    title = "Is Confirmed Speaker"
    parameter_name = "is_confirmed_speaker"

    def lookups(self, request, model_admin):
        return (
            (True, "Yes"),
            (False, "No"),
        )

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(is_confirmed_speaker=self.value())
        return queryset


@admin.register(Grant)
class GrantAdmin(ExportMixin, ConferencePermissionMixin, admin.ModelAdmin):
    change_list_template = "admin/grants/grant/change_list.html"
    resource_class = GrantResource
    form = GrantAdminForm
    list_display = (
        "user_display_name",
        "country",
        "is_proposed_speaker",
        "is_confirmed_speaker",
        "conference",
        "status",
        "approved_type",
        "ticket_amount",
        "travel_amount",
        "accommodation_amount",
        "total_amount",
        "country_type",
        "applicant_reply_sent_at",
        "applicant_reply_deadline",
        "voucher_code",
        "voucher_email_sent_at",
        "created",
    )
    readonly_fields = (
        "applicant_message",
        "plain_thread_id",
    )
    list_filter = (
        "conference",
        "status",
        "country_type",
        "occupation",
        "grant_type",
        "interested_in_volunteering",
        "needs_funds_for_travel",
        "need_visa",
        "need_accommodation",
        IsProposedSpeakerFilter,
        IsConfirmedSpeakerFilter,
        ("travelling_from", CountryFilter),
    )
    search_fields = (
        "email",
        "full_name",
        "travelling_from",
        "been_to_other_events",
        "why",
        "notes",
    )
    actions = [
        send_reply_emails,
        send_grant_reminder_to_waiting_for_confirmation,
        send_reply_email_waiting_list_update,
        create_grant_vouchers_on_pretix,
        send_voucher_via_email,
        "delete_selected",
    ]
    autocomplete_fields = ("user",)

    fieldsets = (
        (
            "Manage the Grant",
            {
                "fields": (
                    "status",
                    "approved_type",
                    "country_type",
                    "ticket_amount",
                    "travel_amount",
                    "accommodation_amount",
                    "total_amount",
                    "applicant_message",
                    "plain_thread_id",
                    "applicant_reply_sent_at",
                    "applicant_reply_deadline",
                    "pretix_voucher_id",
                    "voucher_code",
                    "voucher_email_sent_at",
                )
            },
        ),
        (
            "About the Applicant",
            {
                "fields": (
                    "name",
                    "full_name",
                    "conference",
                    "user",
                    "age_group",
                    "gender",
                    "occupation",
                )
            },
        ),
        (
            "The Grant",
            {
                "fields": (
                    "grant_type",
                    "needs_funds_for_travel",
                    "need_visa",
                    "need_accommodation",
                    "travelling_from",
                    "why",
                    "python_usage",
                    "been_to_other_events",
                    "community_contribution",
                    "interested_in_volunteering",
                    "notes",
                    "website",
                    "twitter_handle",
                    "github_handle",
                    "linkedin_url",
                    "mastodon_handle",
                )
            },
        ),
    )

    @admin.display(description="User", ordering="user__full_name")
    def user_display_name(self, obj):
        if obj.user_id:
            return obj.user.display_name
        return obj.email

    @admin.display(
        description="C",
    )
    def country(self, obj):
        if obj.travelling_from:
            country = countries.get(code=obj.travelling_from)
            if country:
                return country.emoji

        return ""

    @admin.display(description="✍️")
    def is_proposed_speaker(self, obj):
        if obj.is_proposed_speaker:
            return "✍️"
        return ""

    @admin.display(description="🗣️")
    def is_confirmed_speaker(self, obj):
        if obj.is_confirmed_speaker:
            return "🗣️"
        return ""

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .annotate(
                is_proposed_speaker=Exists(
                    Submission.objects.non_cancelled().filter(
                        conference_id=OuterRef("conference_id"),
                        speaker_id=OuterRef("user_id"),
                    )
                ),
                is_confirmed_speaker=Exists(
                    ScheduleItem.objects.filter(
                        conference_id=OuterRef("conference_id"),
                        submission__speaker_id=OuterRef("user_id"),
                    )
                ),
            )
        )
        return qs

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "summary/",
                self.admin_site.admin_view(self.summary_view),
                name="grants-summary",
            ),
        ]
        return custom_urls + urls

    def summary_view(self, request):
        """
        Custom view for summarizing Grant data in the Django admin.
        Aggregates data by country and status, and applies request filters.
        """
        statuses = Grant.Status.choices

        filtered_grants, formatted_filters = self._filter_and_format_grants(request)

        grants_by_country = filtered_grants.values(
            "travelling_from", "status"
        ).annotate(total=Count("id"))

        (
            country_stats,
            status_totals,
            totals_per_continent,
        ) = self._aggregate_data_by_country(grants_by_country, statuses)
        gender_stats = self._aggregate_data_by_gender(filtered_grants, statuses)
        financial_summary, total_amount = self._aggregate_financial_data_by_status(
            filtered_grants, statuses
        )

        sorted_country_stats = dict(
            sorted(country_stats.items(), key=lambda x: (x[0][0], x[0][2]))
        )

        context = {
            "country_stats": sorted_country_stats,
            "statuses": statuses,
            "genders": {code: name for code, name in GENDERS},
            "financial_summary": financial_summary,
            "total_amount": total_amount,
            "total_grants": filtered_grants.count(),
            "status_totals": status_totals,
            "totals_per_continent": totals_per_continent,
            "gender_stats": gender_stats,
            "filters": formatted_filters,
            **self.admin_site.each_context(request),
        }
        return TemplateResponse(request, "admin/grants/grant_summary.html", context)

    def _aggregate_data_by_country(self, grants_by_country, statuses):
        """
        Aggregates grant data by country and status.
        """

        summary = {}
        status_totals = {status[0]: 0 for status in statuses}
        totals_per_continent = {}

        for data in grants_by_country:
            country = countries.get(code=data["travelling_from"])
            continent = country.continent.name if country else "Unknown"
            country_name = f"{country.name} {country.emoji}" if country else "Unknown"
            country_code = country.code if country else "Unknown"
            key = (continent, country_name, country_code)

            if key not in summary:
                summary[key] = {status[0]: 0 for status in statuses}

            summary[key][data["status"]] += data["total"]
            status_totals[data["status"]] += data["total"]

            # Update continent totals
            if continent not in totals_per_continent:
                totals_per_continent[continent] = {status[0]: 0 for status in statuses}
            totals_per_continent[continent][data["status"]] += data["total"]

        return summary, status_totals, totals_per_continent

    def _aggregate_data_by_gender(self, filtered_grants, statuses):
        """
        Aggregates grant data by gender and status.
        """
        gender_data = filtered_grants.values("gender", "status").annotate(
            total=Count("id")
        )
        gender_summary = {
            gender: {status[0]: 0 for status in statuses} for gender, _ in GENDERS
        }
        gender_summary[""] = {
            status[0]: 0 for status in statuses
        }  # For unspecified genders

        for data in gender_data:
            gender = data["gender"] if data["gender"] else ""
            status = data["status"]
            total = data["total"]
            gender_summary[gender][status] += total

        return gender_summary

    def _aggregate_financial_data_by_status(self, filtered_grants, statuses):
        """
        Aggregates financial data (total amounts) by grant status.
        """
        financial_data = filtered_grants.values("status").annotate(
            total_amount_sum=Sum("total_amount")
        )
        financial_summary = {status[0]: 0 for status in statuses}
        overall_total = 0

        for data in financial_data:
            status = data["status"]
            total_amount = data["total_amount_sum"] or 0
            financial_summary[status] += total_amount
            overall_total += total_amount

        return financial_summary, overall_total

    def _filter_and_format_grants(self, request):
        """
        Filters the Grant queryset based on request parameters and
        formats the filter keys for display.
        """
        field_lookups = [
            "__exact",
            "__in",
            "__gt",
            "__lt",
            "__contains",
            "__startswith",
            "__endswith",
            "__range",
            "__isnull",
        ]

        filter_mapping = {
            "conference__id": "Conference ID",
            "status": "Status",
            "country_type": "Country Type",
            "occupation": "Occupation",
            "grant_type": "Grant Type",
            "travelling_from": "Country",
        }

        # Construct a set of allowed filters
        allowed_filters = {
            f + lookup for f in filter_mapping.keys() for lookup in field_lookups
        }

        def map_filter_key(key):
            """Helper function to map raw filter keys to user-friendly names"""
            base_key = next(
                (
                    key[: -len(lookup)]
                    for lookup in field_lookups
                    if key.endswith(lookup)
                ),
                key,
            )
            return filter_mapping.get(base_key, base_key.capitalize())

        # Apply filtered parameters and format filter keys for display
        raw_filter_params = {
            k: v for k, v in request.GET.items() if k in allowed_filters
        }
        filter_params = {map_filter_key(k): v for k, v in raw_filter_params.items()}

        filtered_grants = Grant.objects.filter(**raw_filter_params)

        return filtered_grants, filter_params

    class Media:
        js = ["admin/js/jquery.init.js"]
