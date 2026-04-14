def calculate_tdee_katch(weight_kg, body_fat_percentage):
    lbm = weight_kg * (1 - (body_fat_percentage / 100))
    bmr = 370 + 21.6 * lbm
    return int(bmr * 1.2)

def calculate_tdee_mifflin(weight_kg, age, height_cm):
    # Unisex version used in code: (10 * W) + (6.25 * H) - (5 * A) - 78
    bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 78
    return int(bmr * 1.2)

w, h, bf, age = 89, 187, 19, 31
print(f"Katch-McArdle: {calculate_tdee_katch(w, bf)}")
print(f"Mifflin-St Jeor: {calculate_tdee_mifflin(w, age, h)}")
