from datetime import date, time
import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from bookings.models import Booking
from doctors.dfs_storage_service import DfsUnavailable
from doctors.models import AvailabilitySlot, MedicalHistory


class MedicalReportUploadTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_root)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

        self.doctor = CustomUser.objects.create_user(
            username='upload-doctor',
            password='test-password',
            role='DOCTOR',
        )
        self.patient = CustomUser.objects.create_user(
            username='upload-patient',
            password='test-password',
            role='PATIENT',
        )
        self.unassociated_patient = CustomUser.objects.create_user(
            username='unassociated-patient',
            password='test-password',
            role='PATIENT',
        )

        slot = AvailabilitySlot.objects.create(
            doctor=self.doctor,
            date=date(2027, 1, 15),
            start_time=time(9),
            end_time=time(9, 30),
        )
        Booking.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            slot=slot,
        )

    def report_data(self, patient=None, uploaded_file=None):
        data = {
            'patient': str((patient or self.patient).pk),
            'condition': 'Annual examination',
            'description': 'Routine report',
            'diagnosis_date': '2026-01-15',
            'status': 'active',
        }
        if uploaded_file:
            data['file_upload'] = uploaded_file
        return data

    def test_doctor_uploads_valid_report_for_booked_patient(self):
        self.client.force_login(self.doctor)

        with patch(
            'doctors.dfs_storage_service.store_report',
            side_effect=lambda file_id, content: file_id,
        ) as store_report:
            response = self.client.post(
                reverse('upload_patient_report'),
                data=self.report_data(
                    uploaded_file=SimpleUploadedFile(
                        'report.pdf',
                        b'%PDF-1.7 medical report',
                    )
                )
            )

        self.assertRedirects(response, reverse('doctor_dashboard'))
        report = MedicalHistory.objects.get(
            doctor=self.doctor,
            patient=self.patient,
        )
        store_report.assert_called_once()
        self.assertEqual(store_report.call_args.args[1], b'%PDF-1.7 medical report')
        self.assertEqual(report.dfs_file_id, store_report.call_args.args[0])
        self.assertEqual(report.original_filename, 'report.pdf')
        self.assertFalse(report.file_upload)

    def test_doctor_cannot_upload_report_for_unassociated_patient(self):
        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse('upload_patient_report'),
            data=self.report_data(patient=self.unassociated_patient),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(
            MedicalHistory.objects.filter(patient=self.unassociated_patient).exists()
        )

    def test_invalid_file_upload_returns_form_error_without_saving(self):
        self.client.force_login(self.doctor)

        with patch('doctors.dfs_storage_service.store_report') as store_report:
            response = self.client.post(
                reverse('upload_patient_report'),
                data=self.report_data(
                    uploaded_file=SimpleUploadedFile('report.pdf', b'not a PDF')
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'does not match its file type')
        store_report.assert_not_called()
        self.assertFalse(MedicalHistory.objects.filter(doctor=self.doctor).exists())

    def test_ajax_upload_returns_updated_report_content(self):
        self.client.force_login(self.doctor)

        with patch(
            'doctors.dfs_storage_service.store_report',
            side_effect=lambda file_id, content: file_id,
        ):
            response = self.client.post(
                f"{reverse('upload_patient_report')}?ajax=1",
                data=self.report_data(
                    uploaded_file=SimpleUploadedFile(
                        'report.pdf',
                        b'%PDF-1.7 medical report',
                    )
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent Patient Reports')
        self.assertContains(response, 'Annual examination')
        self.assertTrue(
            MedicalHistory.objects.filter(
                doctor=self.doctor,
                patient=self.patient,
            ).exists()
        )

    def test_patient_cannot_use_doctor_upload_endpoint(self):
        self.client.force_login(self.patient)

        response = self.client.post(
            reverse('upload_patient_report'),
            data=self.report_data(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('home'))
        self.assertFalse(MedicalHistory.objects.exists())

    def test_dfs_unavailable_does_not_create_report_record(self):
        self.client.force_login(self.doctor)

        with patch(
            'doctors.dfs_storage_service.store_report',
            side_effect=DfsUnavailable,
        ) as store_report:
            response = self.client.post(
                reverse('upload_patient_report'),
                data=self.report_data(
                    uploaded_file=SimpleUploadedFile(
                        'report.pdf',
                        b'%PDF-1.7 medical report',
                    )
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'could not be stored right now')
        self.assertNotContains(response, 'Patient report uploaded successfully')
        store_report.assert_called_once()
        self.assertFalse(MedicalHistory.objects.exists())

    def test_database_save_failure_does_not_report_success(self):
        self.client.force_login(self.doctor)

        with patch(
            'doctors.dfs_storage_service.store_report',
            side_effect=lambda file_id, content: file_id,
        ), patch.object(MedicalHistory, 'save', side_effect=DatabaseError):
            response = self.client.post(
                reverse('upload_patient_report'),
                data=self.report_data(
                    uploaded_file=SimpleUploadedFile(
                        'report.pdf',
                        b'%PDF-1.7 medical report',
                    )
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'could not be saved')
        self.assertNotContains(response, 'Patient report uploaded successfully')
