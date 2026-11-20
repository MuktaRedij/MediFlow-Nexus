from datetime import date
import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser
from doctors.dfs_storage_service import DfsReportNotFound, DfsUnavailable
from doctors.forms import UploadPatientReportForm
from doctors.models import MedicalHistory


class MedicalReportAccessTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_settings = override_settings(MEDIA_ROOT=self.media_root)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

        self.patient = CustomUser.objects.create_user(
            username='patient-one',
            password='test-password',
            role='PATIENT',
        )
        self.other_patient = CustomUser.objects.create_user(
            username='patient-two',
            password='test-password',
            role='PATIENT',
        )
        self.doctor = CustomUser.objects.create_user(
            username='doctor-one',
            password='test-password',
            role='DOCTOR',
        )
        self.other_doctor = CustomUser.objects.create_user(
            username='doctor-two',
            password='test-password',
            role='DOCTOR',
        )
        self.report = self.create_report(self.patient, self.doctor)
        self.other_report = self.create_report(self.other_patient, self.other_doctor)

    def create_report(self, patient, doctor):
        return MedicalHistory.objects.create(
            doctor=doctor,
            patient=patient,
            condition='Annual examination',
            description='Routine report',
            diagnosis_date=date(2026, 1, 15),
        )

    def attach_pdf(self, report, name='report.pdf'):
        report.file_upload.save(
            name,
            SimpleUploadedFile(name, b'%PDF-1.7 test document'),
            save=True,
        )

    def test_patient_report_list_contains_only_own_reports(self):
        self.client.force_login(self.patient)

        response = self.client.get(reverse('patient_medical_reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Annual examination')
        self.assertEqual(list(response.context['reports']), [self.report])
        self.assertNotContains(response, 'No medical reports have been uploaded')

    def test_report_list_requires_patient_role(self):
        self.client.force_login(self.doctor)

        response = self.client.get(reverse('patient_medical_reports'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('home'))

    def test_report_list_requires_authentication(self):
        response = self.client.get(reverse('patient_medical_reports'))

        self.assertRedirects(
            response,
            f"{reverse('home')}?next={reverse('patient_medical_reports')}",
        )

    def test_patient_can_download_own_report(self):
        self.attach_pdf(self.report)
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="report.pdf"')
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.7 test document')

    @patch('doctors.dfs_storage_service.read_report', return_value=b'%PDF-1.7 from DFS')
    def test_patient_can_download_own_dfs_report(self, read_report):
        self.report.dfs_file_id = 'medical-report-test-id'
        self.report.original_filename = 'dfs-report.pdf'
        self.report.save()
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="dfs-report.pdf"',
        )
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.7 from DFS')
        read_report.assert_called_once_with('medical-report-test-id')

    def test_patient_cannot_download_another_patients_report(self):
        self.attach_pdf(self.other_report)
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.other_report.pk])
        )

        self.assertEqual(response.status_code, 404)

    @patch('doctors.dfs_storage_service.read_report')
    def test_patient_cannot_download_another_patients_dfs_report(self, read_report):
        self.other_report.dfs_file_id = 'other-medical-report-id'
        self.other_report.save()
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.other_report.pk])
        )

        self.assertEqual(response.status_code, 404)
        read_report.assert_not_called()

    def test_doctor_can_download_only_own_patient_reports(self):
        self.attach_pdf(self.report)
        self.attach_pdf(self.other_report, name='other-report.pdf')
        self.client.force_login(self.doctor)

        allowed = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )
        denied = self.client.get(
            reverse('download_medical_report', args=[self.other_report.pk])
        )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 404)

    @patch('doctors.dfs_storage_service.read_report', return_value=b'%PDF-1.7 doctor report')
    def test_doctor_can_download_own_dfs_report(self, read_report):
        self.report.dfs_file_id = 'doctor-medical-report-id'
        self.report.original_filename = 'doctor-report.pdf'
        self.report.save()
        self.client.force_login(self.doctor)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            b''.join(response.streaming_content),
            b'%PDF-1.7 doctor report',
        )
        read_report.assert_called_once_with('doctor-medical-report-id')

    @patch('doctors.dfs_storage_service.read_report')
    def test_doctor_cannot_download_another_doctors_dfs_report(self, read_report):
        self.other_report.dfs_file_id = 'other-doctor-medical-report-id'
        self.other_report.save()
        self.client.force_login(self.doctor)

        response = self.client.get(
            reverse('download_medical_report', args=[self.other_report.pk])
        )

        self.assertEqual(response.status_code, 404)
        read_report.assert_not_called()

    def test_download_of_missing_file_returns_404(self):
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_download_of_missing_storage_file_returns_404(self):
        self.attach_pdf(self.report)
        self.report.file_upload.storage.delete(self.report.file_upload.name)
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 404)

    @patch('doctors.dfs_storage_service.read_report', side_effect=DfsReportNotFound)
    def test_missing_dfs_object_returns_404(self, read_report):
        self.report.dfs_file_id = 'missing-medical-report-id'
        self.report.save()
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, 'missing-medical-report-id', status_code=404)
        read_report.assert_called_once_with('missing-medical-report-id')

    @patch('doctors.dfs_storage_service.read_report', side_effect=DfsUnavailable)
    def test_dfs_unavailable_returns_service_unavailable(self, read_report):
        self.report.dfs_file_id = 'medical-report-outage'
        self.report.save()
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'medical-report-outage', status_code=503)
        read_report.assert_called_once_with('medical-report-outage')

    def test_anonymous_user_cannot_download_report(self):
        response = self.client.get(
            reverse('download_medical_report', args=[self.report.pk])
        )

        self.assertEqual(response.status_code, 302)

    def test_public_media_route_does_not_serve_medical_reports(self):
        self.attach_pdf(self.report)

        response = self.client.get(f'/media/{self.report.file_upload.name}')

        self.assertEqual(response.status_code, 404)

    def test_upload_form_rejects_unsupported_file_extension(self):
        form = self.upload_form(
            SimpleUploadedFile('report.exe', b'%PDF-1.7 test document')
        )

        self.assertIn('file_upload', form.errors)

    def test_upload_form_rejects_content_that_does_not_match_extension(self):
        form = self.upload_form(SimpleUploadedFile('report.pdf', b'not a PDF'))

        self.assertIn('file_upload', form.errors)

    def test_upload_form_rejects_oversized_file(self):
        form = self.upload_form(
            SimpleUploadedFile('report.pdf', b'%PDF-' + b'x' * (10 * 1024 * 1024))
        )

        self.assertIn('file_upload', form.errors)

    def upload_form(self, uploaded_file):
        return UploadPatientReportForm(
            doctor=self.doctor,
            data={
                'patient': str(self.patient.pk),
                'condition': 'Annual examination',
                'description': 'Routine report',
                'diagnosis_date': '2026-01-15',
                'status': 'active',
            },
            files={'file_upload': uploaded_file},
        )
