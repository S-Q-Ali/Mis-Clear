"""ScanCreate validation: image scans need no target label (photo uploads later)."""

import pytest
from pydantic import ValidationError

from app.backend.schemas import ScanCreate


def test_image_scan_accepts_blank_target_value():
    scan = ScanCreate(targetType="image", targetValue="  ")

    assert scan.targetValue == "(image)"


def test_image_scan_keeps_label_when_provided():
    scan = ScanCreate(targetType="image", targetValue="front-door-photo")

    assert scan.targetValue == "front-door-photo"


@pytest.mark.parametrize("target_type", ["email", "username", "custom"])
def test_blank_target_value_still_rejected_for_other_types(target_type):
    with pytest.raises(ValidationError):
        ScanCreate(targetType=target_type, targetValue="")


def test_email_target_requires_valid_email():
    with pytest.raises(ValidationError):
        ScanCreate(targetType="email", targetValue="not-an-email")