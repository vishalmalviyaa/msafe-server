from django.db import migrations


def create_default_accounts(apps, schema_editor):

    User = apps.get_model("scalability_core", "User")
    ManagerProfile = apps.get_model("manager", "ManagerProfile")

    # =====================
    # OWNER ACCOUNT
    # =====================

    if not User.objects.filter(username="owner").exists():

        owner = User(
            username="owner",
            email="owner@msafe.com",
            is_staff=True,
            is_superuser=True
        )
        owner.set_password("owner123")
        owner.save()

    # =====================
    # MANAGER ACCOUNT
    # =====================

    if not User.objects.filter(username="manager").exists():

        manager_user = User(
            username="manager",
            email="manager@msafe.com"
        )
        manager_user.set_password("manager123")
        manager_user.save()

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