from datetime import datetime

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.forms import inlineformset_factory

from chrono_scraper.utils.datetime_utils import date_not_in_future
from projects.models import Domain, Project


class DomainInlineForm(forms.ModelForm):
    domain_name = forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": "Enter domain name here"}), required=True
    )
    from_date = forms.DateField(
        widget=forms.DateInput(attrs={"placeholder": "01-01-1990"}),
        required=False,
        help_text="Leave empty for 01-01-1990",
        input_formats=["%d-%m-%Y"],
    )
    to_date = forms.DateField(
        widget=forms.DateInput(attrs={"placeholder": "30-01-2024"}),
        required=False,
        help_text="Leave empty for today",
        input_formats=["%d-%m-%Y"],
    )

    class Meta:
        model = Domain
        exclude = [
            "project",
            "active",
            "created_at",
            "updated_at",
        ]
        hidden_fields = (
            [
                "id",
            ],
        )
        error_messages = {
            "domain_name": {
                "required": "Please enter the domain name",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_class = " domain-row-wrapper"
        self.helper.label_class = ""
        self.helper.field_class = ""
        self.helper.disable_csrf = True

    def clean_domain_name(self):
        domain_name = self.cleaned_data.get("domain_name")

        if not domain_name:
            raise ValidationError("Please enter a domain name.")

        domain_name = domain_name.replace("http://", "")
        domain_name = domain_name.replace("https://", "")
        domain_name = domain_name.replace("www.", "")
        domain_name = domain_name.replace("/", "")

        # Validate that domain_name is a valid URL
        validate = URLValidator()
        try:
            validate(f"https://{domain_name}")
        except ValidationError:
            raise ValidationError("Invalid domain name. Please enter a valid URL.")

        domain_name = domain_name.replace("https://", "")
        return domain_name

    def clean_from_date(self):
        from_date = self.cleaned_data.get("from_date")

        if not from_date:
            return datetime(1990, 1, 1)

        # if valid_date_format(from_date):
        #     raise ValidationError("Incorrect data format, should be DD-MM-YYYY")

        if not date_not_in_future(from_date):
            raise ValidationError("Date cannot be in the future")

        return from_date

    def clean_to_date(self):
        to_date = self.cleaned_data.get("to_date")

        if not to_date:
            return datetime.now()

        # if not valid_date_format(to_date):
        #     raise ValidationError("Incorrect data format, should be DD-MM-YYYY")

        if not date_not_in_future(to_date):
            raise ValidationError("Date cannot be in the future")

        return to_date

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")

        if from_date and to_date:
            # Check if from_date is after to_date
            if from_date > to_date:
                raise ValidationError("From date must be before to date.")

        return cleaned_data


DomainInlineFormSet = inlineformset_factory(
    Project,
    Domain,
    form=DomainInlineForm,
    fields=[
        "id",
        "domain_name",
        "from_date",
        "to_date",
    ],
    can_delete=False,
    can_delete_extra=True,
    extra=0,
    min_num=1,
    fk_name="project",
)


DomainInlineUpdateFormSet = inlineformset_factory(
    Project,
    Domain,
    form=DomainInlineForm,
    fields=[
        "id",
        "domain_name",
        "from_date",
        "to_date",
    ],
    can_delete=True,
    extra=1,
    can_delete_extra=True,
    min_num=1,
    fk_name="project",
)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        exclude = [
            "user",
            "index_name",
            "status",
            "index_search_key",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_id = "project-form"
        self.helper.form_class = ""
        self.helper.label_class = ""
        self.helper.field_class = ""
