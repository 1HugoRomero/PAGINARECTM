// Módulo de acceso: botón «ojo» para mostrar u ocultar contraseñas (login, registro y restablecer).
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-eye]');
  if (!button) return;
  const input = document.getElementById(button.dataset.eye);
  if (!input) return;
  const hidden = input.type === 'password';
  input.type = hidden ? 'text' : 'password';
  button.classList.toggle('is-open', hidden);
  button.setAttribute('aria-label', hidden ? 'Ocultar contraseña' : 'Mostrar contraseña');
});
