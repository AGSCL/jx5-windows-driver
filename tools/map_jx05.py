"""Asistente breve de mapeo; no captura botones ni emite teclas."""
import argparse
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / '.jx05-monitor/buttons.json'
DEFAULTS = dict(upper='previous', lower='next', left='previous', right='next', center='none')
LABELS = dict(upper='Superior', lower='Inferior', left='Izquierdo', right='Derecho', center='Central')
ACTIONS = dict(previous='Retroceder', next='Avanzar', none='Sin asignar',
               powerpoint='Entrar/salir de presentación en PowerPoint',
               google='Presentar/salir de pantalla completa en Google Slides', xaringan='Pantalla completa en xaringan')


def validate(mapping):
    if not isinstance(mapping, dict) or mapping.keys() != DEFAULTS.keys():
        raise ValueError('El mapa debe contener los cinco botones.')
    if any(not isinstance(value, str) or value not in ACTIONS for value in mapping.values()):
        raise ValueError('Acción desconocida en el mapa de botones.')
    if any(mapping[button] not in ('previous', 'next', 'none') for button in DEFAULTS if button != 'center'):
        raise ValueError('Los botones que repiten solo admiten avanzar, retroceder o sin asignar.')
    return mapping


def load(path=PATH):
    return validate(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else DEFAULTS.copy()


def save(mapping, path=PATH):
    validate(mapping)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--show', action='store_true', help='Mostrar el mapa sin modificarlo')
    args = parser.parse_args()
    mapping = load()
    if not args.show:
        print('1 = Retroceder; 2 = Avanzar; 0 = Sin asignar. Enter conserva la función.')
        print('No pulses el anillo: este asistente configura las funciones con el teclado.')
        choices = {'1': 'previous', '2': 'next', '0': 'none'}
        for button in ('upper', 'lower', 'left', 'right'):
            while True:
                answer = input(f'{LABELS[button]} [{ACTIONS[mapping[button]]}]: ').strip()
                if not answer:
                    break
                if answer in choices:
                    mapping[button] = choices[answer]
                    break
                print('Elige 0, 1, 2 o Enter.')
        print('Central: 0 = Sin asignar; 3 = Entrar/salir PowerPoint; 4 = Presentar Google Slides;')
        print('5 = Pantalla completa xaringan. Elige según la aplicación que pondrás en primer plano.')
        choices = {'0': 'none', '3': 'powerpoint', '4': 'google', '5': 'xaringan'}
        while True:
            answer = input(f'Central [{ACTIONS[mapping["center"]]}]: ').strip()
            if not answer:
                break
            if answer in choices:
                mapping['center'] = choices[answer]
                break
            print('Elige 0, 3, 4, 5 o Enter.')
        save(mapping)
        print('Guardado. Desactiva y activa el modo presentador para aplicar el mapa.')
    for button, action in mapping.items():
        print(f'{LABELS[button]}: {ACTIONS[action]}')
    print('Central: pulsación corta; mantener >=3 s apaga el anillo. No se configura repetición.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc))
