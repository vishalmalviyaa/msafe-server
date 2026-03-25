from django.db import migrations


def create_default_accounts(apps, schema_editor):

    User = apps.get_model("auth", "User")
    ManagerProfile = apps.get_model("manager", "ManagerProfile")

    # =====================
    # OWNER ACCOUNT
    # =====================

    if not User.objects.filter(username="owner").exists():

        owner = User.objects.create_superuser(
            username="owner",
            email="owner@msafe.com",
            password="owner123"
        )

    # =====================
    # MANAGER ACCOUNT
    # =====================

    if not User.objects.filter(username="manager").exists():

        manager_user = User.objects.create_user(
            username="manager",
            email="manager@msafe.com",
            password="manager123"
        )

        ManagerProfile.objects.create(
            user=manager_user,
            phone="9999999999",
            total_keys=100,
            used_keys=0
        )


class Migration(migrations.Migration):

    dependencies = [
        ("scalability_core", "0001_initial"),
        ("manager", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_accounts),
    ]