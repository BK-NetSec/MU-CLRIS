"""
MU-CLRIS | Automated Resource Versioning Logic
===============================================
Author : Bahabelom Kiros (Tomas) | GitHub: @BK-NetSec
Project: Mekelle University Centralized Local Resource and
         Information Sharing System (MU-CLRIS)

Overrides ``perform_create`` on the Resource ViewSet to:
  1. Enforce departmental data isolation (security check).
  2. Automatically calculate the next version number for a resource
     with the same title under the same course (V_new = V_current + 1).
  3. Extract basic file metadata (size, type).
  4. Write an audit-log entry for accountability.

Note: this is a reference snippet extracted from the ViewSet. Model,
serializer and import paths are illustrative and depend on your project layout.
"""

from django.db import transaction
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

# Adjust these imports to match your app structure
from .models import Resource, AuditLog
from .serializers import ResourceSerializer
from .permissions import IsDepartmentInstructor


class ResourceViewSet(viewsets.ModelViewSet):
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = [IsDepartmentInstructor]

    def perform_create(self, serializer):
        title = serializer.validated_data.get("title")
        course = serializer.validated_data.get("course")
        user = self.request.user

        # ------------------------------------------------------------------
        # 1. SECURITY CHECK: Departmental data isolation
        #    Non-staff users may only upload to courses in their own department.
        # ------------------------------------------------------------------
        if not user.is_staff and course.department != user.department:
            raise PermissionDenied(
                "You cannot upload a resource to another department's course."
            )

        # ------------------------------------------------------------------
        # 2. VERSION LOGIC
        #    Find the highest existing version for this title + course.
        #    If none exists -> Version 1; otherwise -> highest + 1.
        #    The transaction + row lock prevents two simultaneous uploads
        #    from receiving the same version number.
        # ------------------------------------------------------------------
        uploaded_file = self.request.data.get("file")
        if uploaded_file is None:
            raise ValidationError({"file": "No file was submitted."})

        with transaction.atomic():
            latest = (
                Resource.objects.select_for_update()
                .filter(title=title, course=course)
                .order_by("-version")
                .first()
            )
            new_version = latest.version + 1 if latest else 1

            # --------------------------------------------------------------
            # 3. AUTO METADATA EXTRACTION
            # --------------------------------------------------------------
            file_size = uploaded_file.size
            file_type = uploaded_file.name.rsplit(".", 1)[-1].upper()

            # Single save with all calculated fields
            resource = serializer.save(
                uploaded_by=user,
                version=new_version,
                file_size=file_size,
                file_type=file_type,
            )

            # --------------------------------------------------------------
            # 4. AUDIT LOG ENTRY
            # --------------------------------------------------------------
            AuditLog.objects.create(
                user=user,
                action="UPLOADED",
                resource_title=resource.title,
            )
