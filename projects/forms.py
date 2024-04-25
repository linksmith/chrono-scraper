from datetime import datetime

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from chrono_scraper.utils.datetime_utils import date_not_in_future
from chrono_scraper.utils.url_utils import percent_encode_url, strip_and_clean_url, validate_url
from projects.models import CdxQuery, Project


class CdxQueryInlineForm(forms.ModelForm):
    url = forms.CharField(widget=forms.TextInput(attrs={"placeholder": "Enter URL here"}), required=True)
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
        model = CdxQuery
        exclude = [
            "project",
            "created_at",
            "updated_at",
        ]
        hidden_fields = (
            [
                "id",
            ],
        )
        error_messages = {
            "url": {
                "required": "Please enter a valid URL",
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

    def clean_url(self):
        url = self.cleaned_data.get("url")

        if not url:
            raise ValidationError("Please enter a valid URL")

        url = validate_url(url)
        url = strip_and_clean_url(url)
        url = percent_encode_url(url)

        return url

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


CdxQueryInlineCreateFormSet = inlineformset_factory(
    Project,
    CdxQuery,
    form=CdxQueryInlineForm,
    fields=[
        "id",
        "url",
        "from_date",
        "to_date",
    ],
    can_delete=False,
    can_delete_extra=True,
    extra=0,
    min_num=1,
    fk_name="project",
)


CdxQueryInlineUpdateFormSet = inlineformset_factory(
    Project,
    CdxQuery,
    form=CdxQueryInlineForm,
    fields=[
        "id",
        "url",
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
            "status",
            "index_name",
            "index_search_key",
            "index_task_id",
            "index_start_time",
            "index_end_time",
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
