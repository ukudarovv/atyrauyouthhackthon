from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    required_roles: tuple[str, ...] = ()
    
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.role in self.required_roles)

class OwnerRequiredMixin(RoleRequiredMixin):
    required_roles = ('owner',)

class ManagerRequiredMixin(RoleRequiredMixin):
    required_roles = ('manager', 'owner')

class CashierRequiredMixin(RoleRequiredMixin):
    required_roles = ('cashier', 'manager', 'owner')
