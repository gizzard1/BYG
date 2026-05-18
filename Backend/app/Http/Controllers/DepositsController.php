<?php

namespace App\Http\Controllers;

use App\Models\Container;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\Process\Process;

class DepositsController extends Controller
{
    private static function getPythonExecutable()
    {
        $venvPython = base_path('../model/.venv/bin/python');

        if (file_exists($venvPython)) {
            return $venvPython;
        }

        return 'python3';
    }

    public static function loadDeposits(Request $request)
    {
        try {
            $user = $request->user();
            $deposits = $user->deposits; // Suponiendo que tienes una relación definida en el modelo User
            $balance = $deposits->sum('bonus'); // Suma de los montos de los depósitos
            return ['deposits' => $deposits, 'balance' => $balance];
        } catch (\Throwable $th) {
            Log::error($th->getMessage());
            return response()->json(['error' => 'Error al cargar los depósitos'], 500);
        }
    }
    private static function manageDoor($pass, $command)
    {
        // Preparar comando para enviar señal de cierre al contenedor vía websocket
        $command = $pass . ':' . $command;
        $scriptPath = base_path('app/Http/Controllers/websocket.py');
        $python = self::getPythonExecutable();

        // Enviar señal para cerrar el contenedor por al websocket IP al puerto 81 con el mensaje "PASSWORD:P0"
        $process = new Process([$python, $scriptPath, $command]);
        $process->run();

        if (!$process->isSuccessful()) {
            Log::error('Error ejecutando websocket.py', [
                'script' => $scriptPath,
                'command' => $command,
                'exit_code' => $process->getExitCode(),
                'stdout' => $process->getOutput(),
                'stderr' => $process->getErrorOutput(),
            ]);
        }

        if ($command === '181') self::manageDoor($pass, 'P1');
    }
    private static function storeTempImage($imgDecoded, $mimeType = 'image/jpeg')
    {

        $fp_dir = storage_path('app/public/temp');
        $extension = $mimeType === 'image/png' ? '.png' : '.jpg';
        $path = $fp_dir . '/' . uniqid() . $extension;
        // Asegurar que el directorio exista
        if (!file_exists($fp_dir)) {
            mkdir($fp_dir, 0755, true);
        }

        // Guardar la imagen
        file_put_contents($path, $imgDecoded);
        return $path;
    }
    private static function decodeQR($imagePath)
    {
        // Analizar QR en script python en los controladores
        $scriptPath = base_path('app/Http/Controllers/qr-decoder.py');
        $python = self::getPythonExecutable();

        $process = new Process([$python, $scriptPath, $imagePath]);
        $process->run();

        if (!$process->isSuccessful()) {
            Log::error('Error ejecutando qr-decoder.py', [
                'script' => $scriptPath,
                'image_path' => $imagePath,
                'exit_code' => $process->getExitCode(),
                'stdout' => $process->getOutput(),
                'stderr' => $process->getErrorOutput(),
            ]);
            return null;
        }

        return trim($process->getOutput());
    }
    private static function analyzeImage($formData)
    {
        $scriptPath2 = base_path('app/Http/Controllers/image-analyzer.py');
        $python = self::getPythonExecutable();

        $process = new Process([$python, $scriptPath2]);

        $process->setInput(json_encode([
            'img64' => $formData,
            'openai_api_key' => config('services.openai.api_key'),
        ]));

        $process->run();

        if (!$process->isSuccessful()) {
            Log::error('Error ejecutando image-analyzer.py', [
                'script' => $scriptPath2,
                'exit_code' => $process->getExitCode(),
                'stdout' => $process->getOutput(),
                'stderr' => $process->getErrorOutput(),
            ]);
        }

        return $process;
    }
    public static function storeDeposit(Request $request)
    {
        try {
            $img64 = $request->input('img');
            $user = $request->user();

            if (!$img64) {
                return response()->json(['error' => 'image_required']);
            }

            $mimeType = 'image/jpeg';
            if (preg_match('/^data:(image\/[a-zA-Z0-9.+-]+);base64,/', $img64, $matches)) {
                $mimeType = $matches[1];
            }

            $img = preg_replace('/^data:image\/[a-zA-Z0-9.+-]+;base64,/', '', $img64);
            $imgDecoded = base64_decode($img);

            if ($imgDecoded === false) {
                return response()->json(['error' => 'invalid_image']);
            }

            $imagePath = self::storeTempImage($imgDecoded, $mimeType);
            $output = self::decodeQR($imagePath);
            Log::info([$output,$imagePath,!file_exists($imagePath)]);

            // Delimitar id del contenedor por guión medio y buscar por id se recibe '(\'contenedor-1\',)'
            $text = str_replace(['(', ')', '\''], '', $output);
            $id = explode('-', $text)[1] ?? null;
            $container = Container::find($id);
            Log::info([$id]);

            if ($output === null || $container === null) {
                unlink($imagePath);
                return response()->json(['error' => 'invalid_qr']);
            }

            self::manageDoor($container->password, 'P0');

            sleep(1);

            $process = self::analyzeImage($img64);

            if (!$process->isSuccessful()) {
                self::manageDoor($container->password, 'P1');
                return response()->json(['error' => 'no_detected']);
            }

            $result = json_decode($process->getOutput(), true);

            // Eliminar imagen temporal
            unlink($imagePath);

            if (!$result['is_garbage'] || in_array($result['type'], ['rechazo', 'desconocido','many_categories','no_identified'])) {
                self::manageDoor($container->password, '181');
                return response()->json(['error' => 'no_detected']);
            }
            if($result['type'] === 'many_categories'){
                self::manageDoor($container->password, '181');
                return response()->json(['error' => 'many_categories']);
            }
            // Crear depósito
            $deposit = $user->deposits()->create([
                'container_id' => $container->id,
                'user_id' => $user->id,
                'bonus' => $result['bonus'],
                'type' => $result['type'],
            ]);

            self::activator($result['type'], $container->password);

            sleep(2);

            self::manageDoor($container->password, 'P1');

            return response()->json(['success' => true, 'deposit' => $deposit]);
        } catch (\Throwable $th) {
            Log::error($th->getMessage());
            return response()->json(['error' => 'no_detected'], 500);
        }
    }
    private static function activator($type, $pass)
    {
        $activators = [
            'orgánico' => '21',
            'papel/cartón' => '51',
            'envase plástico/lata' => '41',
        ];

        self::manageDoor($pass, $activators[$type]);
    }
}
