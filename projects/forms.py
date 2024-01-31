from datetime import datetime

from crispy_forms.helper import FormHelper
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.forms import inlineformset_factory

from projects.models import Domain, Project


class DomainInlineForm(forms.ModelForm):
    domain_name = forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": "Enter domain name here"}), required=True
    )
    from_date = forms.DateField(widget=forms.DateInput(attrs={"placeholder": "Enter from date here"}), required=False)
    to_date = forms.DateField(widget=forms.DateInput(attrs={"placeholder": "Enter to date here"}), required=False)

    class Meta:
        model = Domain
        exclude = [
            "project",
            "active",
            "created_at",
            "updated_at",
        ]
        hidden_fields = [
            "id",
        ]
        error_messages = {
            "domain_name": {
                "required": "Please enter the domain name",
            },
            "from_date": {
                "required": "Please enter the from date",
            },
            "to_date": {
                "required": "Please enter the to date",
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
            from_date = datetime(1990, 1, 1)
        else:
            # validate input like 30/01/1990
            try:
                datetime.strptime(str(from_date), "%d/%m/%Y")
            except ValueError:
                raise ValidationError("Incorrect data format, should be DD/MM/YYYY")
        return from_date

    def clean_to_date(self):
        to_date = self.cleaned_data.get("to_date")
        if not to_date:
            to_date = datetime.now()
        else:
            try:
                datetime.strptime(str(to_date), "%d/%m/%Y")
            except ValueError:
                raise ValidationError("Incorrect data format, should be DD/MM/YYYY")

        return to_date


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
